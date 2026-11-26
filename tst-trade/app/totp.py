"""İkiqat yoxlama (2FA, owner 2026-11-26 after three failed logins from Beijing): the owner's login needs, besides the
password, the 6-digit code of an authenticator app (Google Authenticator, Microsoft Authenticator, Apple Passwords).

Standard TOTP (RFC 6238: SHA-1, 6 digits, 30 seconds), no extra library. The secret lives only in the server's database,
sealed with the session secret (like the API keys); the browser sees it once, while the owner adds it to the app.
A code is accepted one step early or late (clock drift) and never twice. Eight one-time recovery codes (only their
hashes are kept) open the door if the phone is lost. The guest login (view only) is not affected."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote

from . import auth
from .db import DB
from .seal import seal, unseal

STEP, DIGITS, WINDOW = 30, 6, 1
KEY, PENDING, RECOVERY = "auth:totp", "auth:totp_pending", "auth:totp_recovery"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code(secret: str, t: float | None = None, step_no: int | None = None) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    n = int((time.time() if t is None else t) // STEP) if step_no is None else step_no
    h = hmac.new(key, struct.pack(">Q", n), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    v = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS
    return str(v).zfill(DIGITS)


def match(secret: str, given: str, now: float | None = None, after_step: int = -1) -> int | None:
    """The step the code belongs to (within ±WINDOW), only if it is later than the last accepted one; else None."""
    given = "".join(ch for ch in str(given or "") if ch.isdigit())
    if len(given) != DIGITS:
        return None
    n = int((time.time() if now is None else now) // STEP)
    for s in range(n - WINDOW, n + WINDOW + 1):
        if s > after_step and hmac.compare_digest(code(secret, step_no=s), given):
            return s
    return None


def uri(secret: str) -> str:
    return (f"otpauth://totp/{quote('TST Trade')}:{quote('sahib')}?secret={secret}&issuer={quote('TST Trade')}"
            f"&digits={DIGITS}&period={STEP}")


# ---------- stored state ----------
def _load(db: DB, key: str, sealer: str) -> dict | None:
    raw = db.get(key)
    if not raw:
        return None
    text = unseal(raw, sealer)
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def enabled(db: DB, sealer: str) -> bool:
    st = _load(db, KEY, sealer)
    return bool(st and st.get("secret"))


def status(db: DB, sealer: str) -> dict:
    return {"on": enabled(db, sealer), "recovery_left": len(json.loads(db.get(RECOVERY) or "[]"))}


def start(db: DB, sealer: str) -> dict:
    """A new secret waiting for the first correct code (nothing changes for the login until it is confirmed)."""
    sec = new_secret()
    db.put(PENDING, seal(json.dumps({"secret": sec, "ts": time.time()}), sealer))
    return {"secret": sec, "uri": uri(sec)}


def confirm(db: DB, sealer: str, given: str, now: float | None = None) -> list[str]:
    """Switch 2FA on with the pending secret if the code is right; returns the recovery codes (shown once)."""
    p = _load(db, PENDING, sealer)
    if not p or time.time() - p.get("ts", 0) > 1800:
        raise ValueError("əvvəlcə «2FA qur» düyməsini basın (açar 30 dəqiqə etibarlıdır)")
    s = match(p["secret"], given, now)
    if s is None:
        raise ValueError("kod səhvdir: proqramdakı ən son 6 rəqəmi yazın (telefonun saatı dəqiq olmalıdır)")
    codes = [f"{secrets.randbelow(10**4):04d}-{secrets.randbelow(10**4):04d}" for _ in range(8)]
    db.put(KEY, seal(json.dumps({"secret": p["secret"], "last": s}), sealer))
    db.put(RECOVERY, json.dumps([auth.hash_password(c) for c in codes]))
    db.delete(PENDING)
    return codes


def check(db: DB, sealer: str, given: str, now: float | None = None) -> str | None:
    """The login's second step: 'code' or 'recovery' when accepted (a recovery code is spent), None otherwise."""
    st = _load(db, KEY, sealer)
    if not st:
        return "off"
    s = match(st["secret"], given, now, int(st.get("last", -1)))
    if s is not None:
        db.put(KEY, seal(json.dumps({**st, "last": s}), sealer))
        return "code"
    g = str(given or "").strip()
    if len(g) == 9 and g[4] == "-":
        hashes = json.loads(db.get(RECOVERY) or "[]")
        for h in hashes:
            if auth.verify_hash(g, h):
                hashes.remove(h)
                db.put(RECOVERY, json.dumps(hashes))
                return "recovery"
    return None


def turn_off(db: DB, sealer: str, given: str, now: float | None = None) -> None:
    if check(db, sealer, given, now) is None:
        raise ValueError("kod səhvdir: söndürmək üçün proqramdakı kod və ya ehtiyat kod lazımdır")
    for k in (KEY, PENDING, RECOVERY):
        db.delete(k)
