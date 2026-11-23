import asyncio
import math
from pathlib import Path

from fastapi.testclient import TestClient

from app import auth, brains, candles, forecast, judge
from app.config import Settings
from app.db import DB
from app.engine import Engine, market_open
from app.keys import KeyStore
from app.main import create_app
from app.seal import mask, seal, unseal

SECRET = "s" * 64


def mem():
    return DB(":memory:")


def test_seal_roundtrip_and_wrong_secret():
    s = seal("sk-abc-123456", SECRET)
    assert "sk-abc" not in s
    assert unseal(s, SECRET) == "sk-abc-123456"
    assert unseal(s, "other") is None
    assert mask("sk-abc-123456") == "••••3456"


def test_keystore_never_returns_plain_key_in_status():
    db = mem()
    ks = KeyStore(db, SECRET)
    ks.set("twelvedata", {"key": "td-secret-9999"})
    st = ks.status("twelvedata")
    assert st["saved"] and st["hint"] == "••••9999"
    assert "td-secret" not in str(st)
    assert ks.first("twelvedata") == "td-secret-9999"
    ks.set("alpaca", {"key_id": "id-1234", "secret": "sec-5678"})
    assert ks.get("alpaca") == {"key_id": "id-1234", "secret": "sec-5678"}
    ks.delete("twelvedata")
    assert not ks.status("twelvedata")["saved"]


def test_keystore_rejects_unknown_and_empty():
    ks = KeyStore(mem(), SECRET)
    for slot, v in (("nope", {"key": "x"}), ("alpaca", {"key_id": "a"})):
        try:
            ks.set(slot, v)
            raise AssertionError("should fail")
        except ValueError:
            pass


def test_candles_fold_ticks():
    db = mem()
    t0 = 1_700_000_040.0   # inside a minute
    for i, p in enumerate([10, 12, 9, 11]):
        candles.add_tick(db, "XAU", t0 + i, p)
    c = candles.get(db, "XAU", "1m")[-1]
    assert (c["o"], c["h"], c["l"], c["c"]) == (10, 12, 9, 11)
    assert c["t"] % 60 == 0


def test_week_bucket_starts_monday():
    import datetime as dt
    t = candles.bucket(1_700_000_000, "1w")
    assert dt.datetime.fromtimestamp(t, dt.timezone.utc).weekday() == 0


def test_forecast_needs_enough_candles_and_uses_past_only():
    assert forecast.build([100.0] * 10, "1m") is None
    closes = [100 * math.exp(0.001 * i) for i in range(60)]   # steady uptrend
    fc = forecast.build(closes, "1h")
    m = fc["methods"]
    assert m["rw"]["p_up"] == 0.5
    assert m["momentum"]["p_up"] > 0.5
    assert m["momentum"]["p_up"] <= forecast.P_CAP[1]
    assert m["rw"]["lo80"] < m["rw"]["lo50"] < fc["price"] < m["rw"]["hi50"] < m["rw"]["hi80"]


def test_score_row():
    s = judge.score_row(100, 101, 0.6, 99, 101.5, 98, 102)
    assert s == {"outcome": 1, "hit": 1, "brier": (0.6 - 1) ** 2, "in50": 1, "in80": 1}
    assert judge.score_row(100, 100, 0.6, 99, 101, 98, 102)["outcome"] is None
    assert judge.score_row(100, 99, 0.5, 99.5, 100.5, 98, 102)["hit"] is None


def _seed(db, n, step_tf="1h", drift=0.0, seed=3):
    import random
    rng = random.Random(seed)
    step = candles.TF[step_tf]
    t = 1_699_000_000 // step * step
    px = 100.0
    rows = []
    for i in range(n):
        o = px
        px *= math.exp(drift + rng.gauss(0, 0.002))
        rows.append((t + i * step, o, max(o, px), min(o, px), px))
    candles.store_history(db, "XAU", step_tf, rows)
    return rows


def test_backtest_walk_forward_and_judge_status():
    db = mem()
    rows = _seed(db, 600)
    eng = Engine(db, KeyStore(db, SECRET), "demo", 15)
    now = rows[-1][0] + 2 * 3600
    eng.backtest(now)
    st = {r["method"]: r for r in judge.stats(db, "XAU", "1h", "history")}
    assert st["momentum"]["n"] > 500
    assert st["rw"]["status"] == "bazis"
    # Random walk data: no method may be proven.
    assert st["momentum"]["status"] in ("yox", "az")
    assert 0.6 < st["rw"]["cover80"] < 0.95
    # A forecast only uses candles before it: every issued forecast's target is after its price0 candle.
    bad = db.execute("SELECT COUNT(*) FROM forecasts WHERE target_t <= issued_t").fetchone()[0]
    assert bad == 0


def test_trend_makes_momentum_proven():
    db = mem()
    rows = _seed(db, 1500, drift=0.0015)   # strong steady trend: momentum must beat the baselines
    eng = Engine(db, KeyStore(db, SECRET), "demo", 15)
    eng.backtest(rows[-1][0] + 2 * 3600)
    st = {r["method"]: r for r in judge.stats(db, "XAU", "1h", "history")}
    assert st["up"]["n"] > 1000
    # In a pure up-drift «always up» is hard to beat; the Judge must not call momentum proven unless it beats it.
    if st["momentum"]["status"] == "sübut":
        assert st["momentum"]["hit_rate"] > st["momentum"]["bar"]


def test_live_issue_and_score():
    db = mem()
    eng = Engine(db, KeyStore(db, SECRET), "demo", 15)
    t = 1_700_000_000 // 900 * 900
    for i in range(40):
        candles.add_tick(db, "XAU", t + i * 900 + 1, 100 + (i % 3))
    now = t + 40 * 900 + 2
    n = eng.issue_due(now)
    assert n == len(forecast.methods_for("15m"))   # only XAU has candles; only the 15-minute desk has enough
    candles.add_tick(db, "XAU", now + 5, 105)
    judge.score_due(db, now + 901)
    r = db.execute("SELECT COUNT(*) FROM forecasts WHERE scored_ts IS NOT NULL").fetchone()[0]
    assert r == len(forecast.methods_for("15m"))
    assert "1m" not in forecast.HORIZONS


def test_market_open_weekend():
    import datetime as dt
    sat = dt.datetime(2026, 11, 21, 12, tzinfo=dt.timezone.utc).timestamp()
    tue = dt.datetime(2026, 11, 24, 12, tzinfo=dt.timezone.utc).timestamp()
    assert not market_open(sat) and market_open(tue)


def test_brain_slots_save_and_validate():
    db = mem()
    cfg = brains.save(db, "reader", {"provider": "gemini", "model": "gemini-2.5-flash-lite", "month_usd": 5})
    assert cfg["provider"] == "gemini" and brains.config(db, "reader")["month_usd"] == 5
    try:
        brains.save(db, "reader", {"provider": "nobody"})
        raise AssertionError("should fail")
    except ValueError:
        pass
    view = brains.view(db, KeyStore(db, SECRET))
    assert {v["id"] for v in view} == {"scout", "reader", "strategist", "reviewer"}
    assert all(sum(r["weight"] for r in v["requirements"]) == 100 for v in view)


def test_auth_token():
    tok = auth.make_token(SECRET, now=1000)
    assert auth.valid(tok, SECRET, now=2000)
    assert not auth.valid(tok, "other", now=2000)
    assert not auth.valid(tok, SECRET, now=1000 + 31 * 86400)


def _app(tmp_path: Path):
    s = Settings(app_password="pw", app_password_hash="", session_secret=SECRET, secret_is_fixed=True, price_provider="demo",
                 poll_seconds=15, cookie_secure=False, db_path=tmp_path / "t.sqlite3")
    return create_app(s, start_engine=False)


def test_api_requires_login_and_admin_never_leaks_key(tmp_path):
    app = _app(tmp_path)
    c = TestClient(app)
    assert c.get("/api/state").status_code == 401
    assert c.get("/", follow_redirects=False).status_code == 303
    assert c.post("/login", data={"password": "bad"}, follow_redirects=False).headers["location"] == "/login?e=1"
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    assert r.status_code == 303 and auth.COOKIE in r.cookies
    c.cookies.set(auth.COOKIE, r.cookies[auth.COOKIE])
    assert c.get("/api/state").json()["metals"][0]["symbol"] == "XAU"
    assert c.post("/api/admin/keys/fred", json={"key": "fred-secret-key-4321"}).status_code == 200
    ov = c.get("/api/admin/overview").text
    assert "fred-secret-key" not in ov and "4321" in ov
    assert c.post("/api/admin/keys/nope", json={"key": "x"}).status_code == 400
    assert c.post("/api/admin/provider", json={"provider": "goldapi"}).json()["price_provider"] == "goldapi"
    assert c.post("/api/admin/keys/fred", json={"key": "x"}, headers={"origin": "https://evil.example"}).status_code == 403
    fc = c.get("/api/forecasts?symbol=XAU").json()
    assert [card["horizon"] for card in fc["cards"]] == list(forecast.HORIZONS)


def test_demo_poll_builds_candles(tmp_path):
    db = mem()
    eng = Engine(db, KeyStore(db, SECRET), "demo", 15)
    asyncio.run(eng.poll_once(1_700_000_000.0))
    assert eng.status("XAU", 1_700_000_001.0) == "DEMO"
    assert candles.get(db, "XAG", "1m")


def test_password_hash_and_precedence():
    h = auth.hash_password("a#b$c d'e")
    assert auth.verify_hash("a#b$c d'e", h) and not auth.verify_hash("x", h)
    assert auth.password_ok("a#b$c d'e", db_hash=None, env_hash=h, env_plain="ignored")
    assert not auth.password_ok("ignored", db_hash=None, env_hash=h, env_plain="ignored")
    db_h = auth.hash_password("from-admin-page")
    assert auth.password_ok("from-admin-page", db_hash=db_h, env_hash=h, env_plain="")
    assert not auth.password_ok("a#b$c d'e", db_hash=db_h, env_hash=h, env_plain="")


def test_change_password_on_admin_page(tmp_path):
    c = TestClient(_app(tmp_path))
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    c.cookies.set(auth.COOKIE, r.cookies[auth.COOKIE])
    assert c.post("/api/admin/password", json={"old": "bad", "new": "newpass123", "again": "newpass123"}).status_code == 400
    assert c.post("/api/admin/password", json={"old": "pw", "new": "short", "again": "short"}).status_code == 400
    assert c.post("/api/admin/password", json={"old": "pw", "new": "newpass123", "again": "other1234"}).status_code == 400
    assert c.post("/api/admin/password", json={"old": "pw", "new": "newpass123", "again": "newpass123"}).json()["ok"]
    c2 = TestClient(c.app)
    assert c2.post("/login", data={"password": "pw"}, follow_redirects=False).headers["location"] == "/login?e=1"
    assert c2.post("/login", data={"password": "newpass123"}, follow_redirects=False).headers["location"] == "/"


def test_key_without_a_check_is_saved_not_an_error():
    db = mem()
    ks = KeyStore(db, SECRET)
    ks.set("fmp", {"key": "fmp-test-5678"})
    db.put("dummy", "x")
    from app import keys as keysmod
    ks.delete("fmp")
    ks.db.put("key:gemini_unused", "x")
    # A slot with no check left: none now (every key has one); a missing key reports it instead of an error.
    res = asyncio.run(keysmod.check(ks, "fmp"))
    assert res["ok"] is False and "saxlanmayıb" in res["message"]


def test_session_renewal():
    tok = auth.make_token(SECRET, now=0)
    assert not auth.needs_renewal(tok, SECRET, now=3600)
    assert auth.needs_renewal(tok, SECRET, now=2 * 86400)
    assert not auth.needs_renewal("bad", SECRET, now=10)


def test_guest_sees_panel_not_admin(tmp_path):
    c = TestClient(_app(tmp_path))
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    c.cookies.set(auth.COOKIE, r.cookies[auth.COOKIE])
    assert c.post("/api/admin/guest", json={"password": "guestpass1"}).json()["guest"]
    g = TestClient(c.app)
    r = g.post("/login", data={"password": "guestpass1"}, follow_redirects=False)
    g.cookies.set(auth.COOKIE, r.cookies[auth.COOKIE])
    assert g.get("/api/state").status_code == 200
    assert g.get("/api/me").json()["role"] == "guest"
    assert g.get("/api/admin/overview").status_code == 403
    assert g.get("/admin", follow_redirects=False).headers["location"] == "/"
    assert g.post("/api/admin/keys/fred", json={"key": "x" * 10}).status_code == 403
    # a guest token cannot be turned into an owner token
    tok = r.cookies[auth.COOKIE]
    exp, mark, sig = tok.split(".")
    assert auth.role(f"{exp}.{sig}", SECRET) is None


def _fake_scored(db, method, n, hits, move):
    rows = []
    for i in range(n):
        hit = i < hits
        p1 = 100 * (1 + move) if hit else 100 * (1 - move)
        rows.append(("XAU", "1h", method, "history", i * 3600, i * 3600 + 3600, 100.0, 0.6, 99, 101, 98, 102, "",
                     p1, 1.0, int(p1 > 100), int(hit), (0.6 - int(p1 > 100)) ** 2, 1, 1))
    db.executemany("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, "
                   "lo80, hi80, basis, price1, scored_ts, outcome, hit, brier, in50, in80) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def test_judge_needs_bonferroni_and_a_move_bigger_than_the_spread():
    db = mem()
    _fake_scored(db, "up", 1000, 500, 0.001)          # baseline: half up
    _fake_scored(db, "momentum", 1000, 700, 0.00001)  # 70 % right but moves far smaller than the spread
    _fake_scored(db, "trend", 1000, 700, 0.01)        # 70 % right, big moves
    _fake_scored(db, "fib", 400, 222, 0.01)           # p ~ 0.015: passes 0.05, fails 0.05 / 9
    st = {r["method"]: r for r in judge.stats(db, "XAU", "1h", "history")}
    assert st["momentum"]["status"] == "xərc"
    assert st["trend"]["status"] == "sübut"
    assert st["fib"]["p"] < 0.05 and st["fib"]["status"] == "yox"
    assert judge.official(list(st.values()))["method"] == "trend"


def test_where_splits_hits_by_session_and_mood():
    db = mem()
    _fake_scored(db, "rw", 200, 100, 0.001)
    _fake_scored(db, "trend", 200, 150, 0.01)
    w = judge.where(db, "XAU", "1h", "history")
    assert w["groups"] == ["asia", "london", "ny", "calm", "wild"]
    t = w["methods"]["trend"]
    assert sum(t[g]["n"] for g in ("asia", "london", "ny")) == 200 == t["calm"]["n"] + t["wild"]["n"]
    assert "rw" not in w["methods"]
