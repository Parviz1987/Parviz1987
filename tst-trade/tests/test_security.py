from fastapi.testclient import TestClient

from app import auth
from app.security import MAX_FAILS, Guard
from tests.test_core import _app


def test_password_guessing_is_blocked_and_logged(tmp_path, monkeypatch):
    import asyncio

    async def no_wait(_):
        return None
    monkeypatch.setattr(asyncio, "sleep", no_wait)
    c = TestClient(_app(tmp_path))
    for _ in range(MAX_FAILS):
        assert c.post("/login", data={"password": "guess"}, follow_redirects=False).headers["location"] == "/login?e=1"
    # blocked now: even the right password waits 15 minutes from this address
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    assert r.headers["location"] == "/login?e=blocked" and auth.COOKIE not in r.cookies
    r = c.get("/api/diag", headers={"Authorization": "Bearer x"})
    assert r.status_code == 429


def test_admin_changes_and_new_address_are_journaled(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    c.cookies.set(auth.COOKIE, r.cookies[auth.COOKIE])
    assert c.post("/api/admin/keys/fred", json={"key": "fred-secret-key-4321"}).status_code == 200
    st = c.get("/api/admin/status").json()
    kinds = [e["kind"] for e in st["security_events"]]
    assert "key_saved" in kinds and "login_ok" in kinds
    assert "fred-secret-key" not in str(st["security_events"])
    h = c.get("/").headers
    assert "default-src 'self'" in h["content-security-policy"] and "max-age" in h["strict-transport-security"]


def test_new_address_after_the_first_is_an_alert(tmp_path):
    from app.db import DB
    g = Guard(DB(":memory:"))
    g.succeeded("1.1.1.1", "owner")
    g.succeeded("1.1.1.1", "owner")
    g.succeeded("9.9.9.9", "owner")
    s = g.summary()
    assert [a["ip"] for a in s["alerts"]] == ["9.9.9.9"] and s["known_ips"] == 2
