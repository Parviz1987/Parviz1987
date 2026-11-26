"""İkiqat yoxlama (2FA): RFC 6238 codes, no reuse, recovery codes spent once, the login needs the code only when on."""
import time

from fastapi.testclient import TestClient

from app import auth, totp
from app.db import DB
from tests.test_core import _app

S = "s" * 64


def test_rfc6238_vector_and_window():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"            # RFC 6238 test key "12345678901234567890"
    assert totp.code(secret, 59) == "287082"
    assert totp.code(secret, 1111111109) == "081804"
    now = 1_800_000_000
    assert totp.match(secret, totp.code(secret, now - 30), now) is not None   # one step late is fine
    assert totp.match(secret, totp.code(secret, now - 90), now) is None


def test_setup_confirm_reuse_recovery_off():
    db = DB(":memory:")
    d = totp.start(db, S)
    assert not totp.enabled(db, S) and d["uri"].startswith("otpauth://totp/")
    now = time.time()
    codes = totp.confirm(db, S, totp.code(d["secret"], now), now)
    assert totp.enabled(db, S) and len(codes) == 8
    c2 = totp.code(d["secret"], now + 30)
    assert totp.check(db, S, c2, now + 30) == "code"
    assert totp.check(db, S, c2, now + 30) is None                     # the same code never twice
    assert totp.check(db, S, codes[0], now + 31) == "recovery"
    assert totp.check(db, S, codes[0], now + 32) is None               # a recovery code works once
    assert totp.status(db, S)["recovery_left"] == 7
    totp.turn_off(db, S, codes[1], now + 33)
    assert not totp.enabled(db, S) and totp.check(db, S, "", now) == "off"


def test_login_needs_the_code_when_on(tmp_path):
    c = TestClient(_app(tmp_path))
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    c.cookies.set(auth.COOKIE, r.cookies[auth.COOKIE])
    d = c.post("/api/admin/2fa/start").json()
    rec = c.post("/api/admin/2fa/confirm", json={"code": totp.code(d["secret"])}).json()["recovery"]
    anon = TestClient(c.app)
    assert anon.post("/login", data={"password": "pw"}, follow_redirects=False).headers["location"] == "/login?e=code"
    assert anon.post("/login", data={"password": "pw", "code": "000000"}, follow_redirects=False).headers["location"] == "/login?e=code"
    ok = anon.post("/login", data={"password": "pw", "code": rec[0]}, follow_redirects=False)
    assert ok.headers["location"] == "/" and auth.COOKIE in ok.cookies
