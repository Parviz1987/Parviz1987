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


def test_candle_check_spots_two_interleaved_sources():
    """Two sources a few dollars apart, alternating: the zig-zag shows as strongly negative lag1 and big jumps."""
    import time as _t
    from app import diag
    from tests.test_core import mem
    db = mem()
    t0 = (int(_t.time()) // 1800 - 400) * 1800
    rows = []
    for i in range(300):
        px = 4000 + i * 0.1 + (3.0 if i % 2 else 0.0)        # every other candle from a source $3 higher
        rows.append(("XAU", "30m", t0 + i * 1800, px, px, px, px))
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'history')", rows)
    r = diag._candle_check(db)["XAU/30m"]
    assert r["lag1"] < -0.5 and r["jumps"] == 0          # opens equal closes here: the zig-zag is close to close


def test_forecast_check_finds_forecasts_issued_on_replaced_prices():
    from app import diag
    from tests.test_core import mem
    db = mem()
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'history')",
                   [("XAU", "30m", 1800 * i, 100, 100, 100, 100) for i in range(1, 5)])
    for i, p0 in ((2, 100.0), (3, 103.0)):     # the second one was issued on a price no longer in the series
        db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, "
                   "lo80, hi80, basis, hit) VALUES('XAU','30m','reversal','history',?,?,?,0.6,0,0,0,0,'',?)",
                   (1800 * i, 1800 * (i + 1), p0, 1))
    r = diag._forecast_check(db)["XAU/30m"]
    assert r["n"] == 2 and r["differ"] == 1
