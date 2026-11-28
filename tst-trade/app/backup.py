"""Gecəlik ehtiyat nüsxə (Block 14): once a night the SQLite database is copied (SQLite's own online backup: safe while
the app writes), compressed, and uploaded to Cloudflare R2 (S3-compatible, free up to 10 GB). If the server is lost,
the data is not. The R2 keys are saved in Admin like every other key (encrypted on the server), never in the repo.

The upload is signed with AWS Signature V4 by hand (no extra library) and streamed from disk (the server has little
memory). The last 7 nights are kept under backups/tst-YYYY-MM-DD.sqlite.gz; older ones are deleted."""
from __future__ import annotations

import datetime as _dt
import gzip
import hashlib
import hmac
import os
import re
import shutil
import sqlite3
import time
from urllib.parse import quote

import httpx

KEEP_DAYS = 7
DEFAULT_BUCKET = "tst-backup"
CHUNK = 1 << 20


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _host(account_id: str) -> str:
    """The R2 address. Cloudflare shows the owner a link «https://<id>.r2.cloudflarestorage.com» (EU buckets:
    «<id>.eu.r2…»); the form asks for the id. Either is accepted: the link is cut down to its host."""
    v = (account_id or "").strip()
    if "://" in v:
        v = v.split("://", 1)[1]
    v = v.split("/", 1)[0].strip()
    return v if v.endswith(".r2.cloudflarestorage.com") else f"{v}.r2.cloudflarestorage.com"


HEX = re.compile(r"^[0-9a-fA-F]+$")


def normalize(creds: dict) -> dict:
    """The three Cloudflare values in whichever box they were pasted (owner 27.11 22:00: the 64-character secret
    landed in the HTTPS box). They look different: the link holds «r2.cloudflarestorage.com», the Secret Access Key is
    64 hex characters, the Access Key ID 32. When each can be told apart, they are put in their own boxes."""
    names = ("access_key_id", "secret_access_key", "account_id")
    vals = [str(creds.get(n) or "").strip() for n in names]
    link = [v for v in vals if "r2.cloudflarestorage.com" in v or "://" in v]
    secret = [v for v in vals if len(v) == 64 and HEX.match(v)]
    access = [v for v in vals if len(v) == 32 and HEX.match(v)]
    if len(link) == 1 and len(secret) == 1 and len(access) == 1:
        return {**creds, "account_id": link[0], "secret_access_key": secret[0], "access_key_id": access[0]}
    return creds


def _id_problem(account_id: str) -> str | None:
    """A plain-language reason why the account_id field cannot be right (no value is shown)."""
    core = _host(account_id).removesuffix(".r2.cloudflarestorage.com").split(".")[0]
    if len(core) != 32 or any(c not in "0123456789abcdef" for c in core.lower()):
        return (f"account_id xanası səhvdir: Cloudflare-in HTTPS linki (https://….r2.cloudflarestorage.com) və ya "
                f"ondakı 32 simvolluq kod olmalıdır, burada {len(core)} simvol var")
    return None


def _headers(creds: dict, method: str, path: str, payload_hash: str, query: str = "",
             now: _dt.datetime | None = None) -> tuple[str, dict]:
    """SigV4 for R2 (region «auto», service «s3»). Returns (url, headers)."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    host = _host(creds["account_id"])
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    canon_headers = f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
    signed = "host;x-amz-content-sha256;x-amz-date"
    canon = "\n".join([method, quote(path), query, canon_headers, signed, payload_hash])
    scope = f"{day}/auto/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canon.encode()).hexdigest()])
    k = _sign(("AWS4" + creds["secret_access_key"]).encode(), day)
    for part in ("auto", "s3", "aws4_request"):
        k = _sign(k, part)
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    auth = (f"AWS4-HMAC-SHA256 Credential={creds['access_key_id']}/{scope}, SignedHeaders={signed}, "
            f"Signature={sig}")
    url = f"https://{host}{quote(path)}" + (f"?{query}" if query else "")
    return url, {"x-amz-date": amz_date, "x-amz-content-sha256": payload_hash, "Authorization": auth}


def _bucket_in_link(account_id: str) -> str:
    """A bucket at the end of the link («https://<id>.r2.cloudflarestorage.com/<bucket>»), if Cloudflare showed one."""
    v = (account_id or "").strip()
    if "://" in v:
        v = v.split("://", 1)[1]
    parts = [p for p in v.split("/")[1:] if p.strip()]
    return parts[0].strip().lower() if parts else ""


async def _call(c: httpx.AsyncClient, creds: dict, method: str, path: str) -> httpx.Response:
    url, h = _headers(creds, method, path, hashlib.sha256(b"").hexdigest())
    return await c.request(method, url, headers=h)


def _why(r: httpx.Response) -> str:
    """Cloudflare's own answer, short: HTTP code and the S3 error code (AccessDenied, NoSuchBucket …)."""
    m = re.search(r"<Code>([^<]{1,60})</Code>", r.text or "")
    return f"HTTP {r.status_code}" + (f" {m.group(1)}" if m else "")


async def resolve(creds: dict) -> tuple[str | None, str]:
    """Which bucket to use. The one written in Admin (or at the end of the link) if Cloudflare has it; else the only
    bucket this key sees (or «tst-backup» among several); else «tst-backup» (or the written name) is created.
    Returns (bucket, how) or (None, what the owner should do)."""
    want = (creds.get("bucket") or "").strip().strip("/").lower() or _bucket_in_link(creds.get("account_id", ""))
    async with httpx.AsyncClient(timeout=20) as c:
        if want:
            r = await _call(c, creds, "HEAD", f"/{want}")
            if r.status_code == 200:
                return want, f"bucket «{want}»"
            if r.status_code in (401, 403):
                return None, (f"açar qəbul olunmadı (HTTP {r.status_code}): Access Key ID və Secret Access Key-i "
                              f"yenidən yapışdırın; açarın icazəsi «Object Read & Write» olmalıdır")
        head = _why(r) if want else "—"
        r = await _call(c, creds, "GET", "/")
        listed = _why(r)
        names = re.findall(r"<Name>([^<]+)</Name>", r.text) if r.status_code == 200 else []
        if len(names) == 1:
            return names[0], f"bucket «{names[0]}» (Cloudflare-də olan yeganə bucket)"
        if DEFAULT_BUCKET in names:
            return DEFAULT_BUCKET, f"bucket «{DEFAULT_BUCKET}»"
        if names:
            return None, ("Cloudflare-də bir neçə bucket var: " + ", ".join(names[:6]) +
                          " — hansına yazılsın, onun adını «Bucket» xanasına yazın")
        new = want or DEFAULT_BUCKET
        r = await _call(c, creds, "PUT", f"/{new}")
        if r.status_code == 200:
            return new, f"bucket «{new}» (sistem özü yaratdı)"
        codes = f"[Cloudflare cavabı: bucket {head}; siyahı {listed}; yaratma {_why(r)}]"
        if r.status_code in (401, 403):
            return None, (f"Cloudflare-də «{new}» adlı bucket yoxdur və açarın onu yaratmağa icazəsi yoxdur: açarın icazəsi "
                          f"«Admin Read & Write» olmalıdır və ya Cloudflare → R2 → Create bucket → ad «{new}» {codes}")
        return None, f"bucket «{new}» yaradılmadı {codes}"


async def check_fix(creds: dict) -> tuple[bool, str, str | None]:
    """Admin's «Yoxla»: the address, the key and the bucket (found or created). Returns (ok, message, bucket)."""
    creds = normalize(creds)
    bad = _id_problem(creds.get("account_id", ""))
    if bad:
        return False, bad, None
    try:
        bucket, how = await resolve(creds)
    except httpx.ConnectError:
        return False, "R2 ünvanına çatmaq olmadı: «HTTPS» xanasındakı linki yoxlayın", None
    if not bucket:
        return False, how, None
    # 27.11: the owner's token was «Object Read only» — seeing the bucket is not enough, the night copy WRITES.
    # A tiny file is written and removed, so «işləyir» means the copy can really be stored.
    body = b"tst-trade yoxlama"
    path = f"/{bucket}/backups/yoxlama.txt"
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            url, h = _headers(creds, "PUT", path, hashlib.sha256(body).hexdigest())
            r = await c.put(url, headers=h, content=body)
            if r.status_code in (401, 403):
                return False, (f"açar yalnız oxuya bilir (HTTP {r.status_code}): Cloudflare → R2 → Manage API tokens → "
                               f"açarın icazəsini «Object Read & Write» və ya «Admin Read & Write» edin"), bucket
            if r.status_code != 200:
                return False, f"sınaq faylı yazılmadı: HTTP {r.status_code}", bucket
            await _call(c, creds, "DELETE", path)
    except httpx.ConnectError:
        return False, "R2 ünvanına çatmaq olmadı: «HTTPS» xanasındakı linki yoxlayın", bucket
    return True, f"işləyir: {how}, yazma sınağı keçdi", bucket


async def check(creds: dict) -> tuple[bool, str]:
    ok, msg, _ = await check_fix(creds)
    return ok, msg


def make_copy(db_path: str, out_dir: str) -> str:
    """SQLite online backup -> gzip. Returns the .gz path (the plain copy is removed)."""
    os.makedirs(out_dir, exist_ok=True)
    plain = os.path.join(out_dir, "backup.sqlite")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(plain)
    try:
        src.backup(dst, pages=4096)
    finally:
        dst.close()
        src.close()
    gz = plain + ".gz"
    with open(plain, "rb") as f, gzip.open(gz, "wb", compresslevel=6) as g:
        shutil.copyfileobj(f, g, CHUNK)
    os.remove(plain)
    return gz


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def upload(creds: dict, gz_path: str, now: float | None = None) -> str:
    """Streams the file to R2 and deletes the copy from KEEP_DAYS ago. Returns the object name."""
    day = _dt.datetime.fromtimestamp(now or time.time(), _dt.timezone.utc).strftime("%Y-%m-%d")
    name = f"backups/tst-{day}.sqlite.gz"
    url, h = _headers(creds, "PUT", f"/{creds['bucket']}/{name}", _sha256_file(gz_path))
    size = os.path.getsize(gz_path)

    def stream():
        with open(gz_path, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK), b""):
                yield chunk
    with httpx.Client(timeout=600) as c:
        r = c.put(url, headers={**h, "Content-Length": str(size)}, content=stream())
        if r.status_code != 200:
            raise RuntimeError(f"R2 yükləmə: HTTP {r.status_code} {r.text[:120]}")
        old = (_dt.datetime.fromtimestamp(now or time.time(), _dt.timezone.utc)
               - _dt.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
        url, h = _headers(creds, "DELETE", f"/{creds['bucket']}/backups/tst-{old}.sqlite.gz", hashlib.sha256(b"").hexdigest())
        c.delete(url, headers=h)
    return name
