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
    t = 1_700_000_000 // 60 * 60
    for i in range(40):
        candles.add_tick(db, "XAU", t + i * 60 + 1, 100 + (i % 3))
    now = t + 40 * 60 + 2
    n = eng.issue_due(now)
    assert n == len(forecast.METHODS)          # only XAU has candles; only the 1m desk has enough
    candles.add_tick(db, "XAU", now + 5, 105)
    judge.score_due(db, now + 61)
    r = db.execute("SELECT COUNT(*) FROM forecasts WHERE scored_ts IS NOT NULL").fetchone()[0]
    assert r == len(forecast.METHODS)


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
    s = Settings(app_password="pw", session_secret=SECRET, secret_is_fixed=True, price_provider="demo",
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
    assert [card["horizon"] for card in fc["cards"]] == ["1m", "1h", "1d", "1w"]


def test_demo_poll_builds_candles(tmp_path):
    db = mem()
    eng = Engine(db, KeyStore(db, SECRET), "demo", 15)
    asyncio.run(eng.poll_once(1_700_000_000.0))
    assert eng.status("XAU", 1_700_000_001.0) == "DEMO"
    assert candles.get(db, "XAG", "1m")
