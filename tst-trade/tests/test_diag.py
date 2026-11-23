import logging

from fastapi.testclient import TestClient

from app import auth
from app.config import Settings
from app.main import create_app

SECRET = "s" * 64


def _client(tmp_path):
    s = Settings(app_password="pw", app_password_hash="", session_secret=SECRET, secret_is_fixed=True,
                 price_provider="demo", poll_seconds=15, cookie_secure=False, db_path=tmp_path / "t.sqlite3")
    c = TestClient(create_app(s, start_engine=False))
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    c.cookies.set(auth.COOKIE, r.cookies[auth.COOKIE])
    return c


def test_diag_needs_token_and_never_shows_keys(tmp_path):
    c = _client(tmp_path)
    assert c.post("/api/admin/keys/fred", json={"key": "fred-very-secret-777"}).status_code == 200
    anon = TestClient(c.app)
    assert anon.get("/api/diag").status_code == 401
    tok = c.post("/api/admin/diag-token").json()["token"]
    assert anon.get("/api/diag", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = anon.get("/api/diag", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.text
    assert "fred-very-secret" not in body and SECRET not in body and '"pw"' not in body
    assert r.json()["keys"]["fred"]["saved"] is True
    # the token cannot open the panel or the admin pages
    assert anon.get("/api/state", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    assert anon.post("/api/admin/diag-token", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_error_journal_groups_and_masks(tmp_path):
    c = _client(tmp_path)
    c.post("/api/admin/keys/fred", json={"key": "fred-very-secret-777"})
    log = logging.getLogger("tst.test")
    for _ in range(3):
        try:
            raise ValueError("failed with fred-very-secret-777")
        except ValueError:
            log.exception("boom fred-very-secret-777")
    tok = c.post("/api/admin/diag-token").json()["token"]
    errs = TestClient(c.app).get("/api/diag", headers={"Authorization": f"Bearer {tok}"}).json()["errors"]
    mine = [e for e in errs if e["logger"] == "tst.test"]
    assert len(mine) == 1 and mine[0]["count"] == 3
    assert "fred-very-secret" not in mine[0]["message"] + mine[0]["trace"]
