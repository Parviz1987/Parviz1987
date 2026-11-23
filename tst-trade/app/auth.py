"""One owner, one password. A signed cookie (HMAC with SESSION_SECRET) keeps the session for 30 days."""
from __future__ import annotations

import hashlib
import hmac
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


def password_ok(given: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())
