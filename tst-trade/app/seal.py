"""Keys at rest. Copied from pj-trade-gold (app/autotrade.py seal / unseal): the SQLite file can be copied into a
backup, the SESSION_SECRET in .env is not, so the database alone does not give a key.
Standard library only: a SHA-256 key stream with an HMAC-SHA-256 tag."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

SEAL = "sealed:v1:"


def _keys_of(secret: str) -> tuple[bytes, bytes]:
    root = hashlib.sha256(("tst-trade-keys:" + secret).encode()).digest()
    return hmac.new(root, b"enc", hashlib.sha256).digest(), hmac.new(root, b"mac", hashlib.sha256).digest()


def _stream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = b""
    i = 0
    while len(out) < n:
        out += hashlib.sha256(key + nonce + i.to_bytes(4, "big")).digest()
        i += 1
    return out[:n]


def seal(text: str, secret: str) -> str:
    enc, mac = _keys_of(secret)
    nonce = os.urandom(16)
    data = text.encode()
    ct = bytes(a ^ b for a, b in zip(data, _stream(enc, nonce, len(data))))
    tag = hmac.new(mac, nonce + ct, hashlib.sha256).digest()[:16]
    return SEAL + base64.b64encode(nonce + ct + tag).decode()


def unseal(text: str, secret: str) -> str | None:
    """None when it cannot be read (another SESSION_SECRET): the key must be entered again."""
    if not text.startswith(SEAL):
        return None
    try:
        raw = base64.b64decode(text[len(SEAL):], validate=True)
    except ValueError:
        return None
    if len(raw) < 32:
        return None
    nonce, ct, tag = raw[:16], raw[16:-16], raw[-16:]
    enc, mac = _keys_of(secret)
    if not hmac.compare_digest(tag, hmac.new(mac, nonce + ct, hashlib.sha256).digest()[:16]):
        return None
    try:
        return bytes(a ^ b for a, b in zip(ct, _stream(enc, nonce, len(ct)))).decode()
    except UnicodeDecodeError:
        return None


def mask(text: str | None) -> str | None:
    if not text:
        return None
    return ("••••" + text[-4:]) if len(text) >= 8 else "••••"
