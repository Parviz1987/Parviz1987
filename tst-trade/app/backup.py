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
import shutil
import sqlite3
import time
from urllib.parse import quote

import httpx

KEEP_DAYS = 7
CHUNK = 1 << 20


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _headers(creds: dict, method: str, path: str, payload_hash: str, query: str = "",
             now: _dt.datetime | None = None) -> tuple[str, dict]:
    """SigV4 for R2 (region «auto», service «s3»). Returns (url, headers)."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    host = f"{creds['account_id']}.r2.cloudflarestorage.com"
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


async def check(creds: dict) -> tuple[bool, str]:
    """Can we see the bucket? (a HEAD on it)"""
    empty = hashlib.sha256(b"").hexdigest()
    url, h = _headers(creds, "HEAD", f"/{creds.get('bucket', '')}", empty)
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.head(url, headers=h)
    if r.status_code == 200:
        return True, "işləyir (bucket görünür)"
    if r.status_code in (401, 403):
        return False, f"açar qəbul olunmadı (HTTP {r.status_code})"
    if r.status_code == 404:
        return False, "bucket tapılmadı: adını yoxlayın"
    return False, f"HTTP {r.status_code}"


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
