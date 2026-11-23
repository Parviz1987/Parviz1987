"""One owner, one password. A signed cookie (HMAC with SESSION_SECRET) keeps the session for 30 days."""
from __future__ import annotations

import hashlib
import hmac
import os
import time

COOKIE = "tst_session"
DAYS = 30


def make_token(secret: str, now: float | None = None) -> str:
    exp = str(int((time.time() if now is None else now) + DAYS * 86400))
    sig = hmac.new(secret.encode(), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def valid(token: str | None, secret: str, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    exp, sig = token.split(".", 1)
    good = hmac.new(secret.encode(), exp.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return False
    try:
        return int(exp) > (time.time() if now is None else now)
    except ValueError:
        return False


def hash_password(pw: str, salt: bytes | None = None) -> str:
    """scrypt (standard library). Stored as scrypt$<salt hex>$<hash hex>."""
    salt = salt or os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_hash(pw: str, stored: str) -> bool:
    try:
        kind, salt, h = stored.split("$")
        if kind != "scrypt":
            return False
        return hmac.compare_digest(hash_password(pw, bytes.fromhex(salt)), stored)
    except ValueError:
        return False


def password_ok(given: str, *, db_hash: str | None, env_hash: str, env_plain: str) -> bool:
    """The password set on the admin page (DB) wins; then APP_PASSWORD_HASH; then APP_PASSWORD."""
    if db_hash:
        return verify_hash(given, db_hash)
    if env_hash:
        return verify_hash(given, env_hash)
    return bool(env_plain) and hmac.compare_digest(given.encode(), env_plain.encode())


MIN_LEN = 8


def needs_renewal(token: str | None, secret: str, now: float | None = None) -> bool:
    """A valid session issued more than a day ago is renewed (sliding 30 days)."""
    now = time.time() if now is None else now
    if not valid(token, secret, now):
        return False
    exp = int(token.split(".", 1)[0])
    return exp - now < (DAYS - 1) * 86400
