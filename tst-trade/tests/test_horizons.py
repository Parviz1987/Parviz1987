import datetime as dt
import math
import random

from app import candles, forecast, judge
from app.db import DB
from app.engine import Engine, MacroLookup, target_time
from app.keys import KeyStore
from app.providers.capital import parse_prices

SECRET = "s" * 64


def _daily(db, n, drift=0.0, seed=5):
    rng = random.Random(seed)
    t = int(dt.datetime(2020, 1, 6, tzinfo=dt.timezone.utc).timestamp())   # a Monday
    px, rows = 100.0, []
    while len(rows) < n:
        if dt.datetime.fromtimestamp(t, dt.timezone.utc).weekday() < 5:
            o = px
            px *= math.exp(drift + rng.gauss(0, 0.01))
            rows.append((t, o, max(o, px) * 1.002, min(o, px) * 0.998, px))
        t += 86400
    candles.store_history(db, "XAU", "1d", rows)
    return rows


def test_multi_day_horizons_score_against_kth_trading_day():
    db = DB(":memory:")
    rows = _daily(db, 400)
    eng = Engine(db, KeyStore(db, SECRET), "demo", 15)
    eng.backtest(rows[-1][0] + 3 * 86400)
    # a 3-day forecast issued at candle i is scored on the close of candle i+2 (weekends skipped)
    by_t = {r[0]: i for i, r in enumerate(rows)}
    for f in db.execute("SELECT issued_t, price1 FROM forecasts WHERE horizon='3d' AND method='rw' "
                        "AND price1 IS NOT NULL LIMIT 50").fetchall():
        i = by_t[f["issued_t"]]
        assert f["price1"] == rows[i + 2][4]
    st = {r["method"]: r for r in judge.stats(db, "XAU", "10d", "history")}
    assert "reversal" not in st and "macro" in st and st["trend"]["n"] > 300
    # overlapping forecasts: the p-value uses about n/10 independent tests, so random data is never "proven"
    assert all(r["status"] != "sübut" for r in st.values())


def test_target_time_skips_weekend():
    fri = int(dt.datetime(2026, 11, 20, tzinfo=dt.timezone.utc).timestamp())
    assert dt.datetime.fromtimestamp(target_time(fri, "3d") - 86400, dt.timezone.utc).weekday() == 1   # Tue
    assert target_time(fri, "1d") == fri + 86400


def test_session_day_bucket():
    sun_late = dt.datetime(2026, 11, 22, 22, 30, tzinfo=dt.timezone.utc).timestamp()
    mon = dt.datetime(2026, 11, 23, tzinfo=dt.timezone.utc).timestamp()
    assert candles.bucket(sun_late, "1d") == mon
    assert candles.bucket(sun_late, "1w") == mon
    assert candles.bucket(mon + 3600, "1d") == mon


def test_signal_methods():
    up = [{"o": 100 + i, "h": 100.5 + i, "l": 99.5 + i, "c": 100 + i} for i in range(200)]
    fc = forecast.build(up, "1d")["methods"]
    assert fc["breakout"]["p_up"] == forecast.SIGNAL_P        # new 20-candle high
    assert fc["rsi"]["p_up"] == 1 - forecast.SIGNAL_P         # RSI 100: overbought
    assert fc["trend"]["p_up"] > 0.5
    assert fc["macro"]["p_up"] == 0.5                         # no FRED data: no view
    m = forecast.build(up, "1d", {"dfii10": -0.2, "dollar": -1.5})["methods"]["macro"]
    assert m["p_up"] > 0.5
    # a swing up then a pullback to the 50 % level -> bounce up
    sw = [{"o": 100, "h": 100, "l": 100, "c": 100}] * 10 + \
         [{"o": 100 + i, "h": 100 + i, "l": 100 + i, "c": 100 + i} for i in range(21)] + \
         [{"o": 120 - i, "h": 120 - i, "l": 120 - i, "c": 120 - i} for i in range(11)]
    p, basis = forecast.fib_view(sw, 0.001)
    assert p == forecast.SIGNAL_P and "50.0" in basis


def test_rsi_flat_and_known():
    assert forecast.rsi([1.0] * 10) is None
    assert forecast.rsi([float(i) for i in range(30)]) == 100.0


def test_macro_lookup_uses_only_past_values():
    db = DB(":memory:")
    from app.feeds import Feeds
    Feeds(db, KeyStore(db, SECRET))
    for i in range(20):
        d = (dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat()
        db.execute("INSERT INTO macro VALUES('DFII10', ?, ?)", (d, 2.0 - 0.01 * i))
        db.execute("INSERT INTO macro VALUES('DTWEXBGS', ?, ?)", (d, 120.0))
    t = int(dt.datetime(2026, 1, 15, tzinfo=dt.timezone.utc).timestamp())
    m = MacroLookup(db).at(t)
    assert abs(m["dfii10"] - (-0.05)) < 1e-9 and m["dollar"] == 0


def test_capital_history_parse_moves_sunday_session_to_monday():
    data = {"prices": [
        {"snapshotTimeUTC": "2026-11-22T22:00:00", "openPrice": {"bid": 1, "ask": 3}, "highPrice": {"bid": 4, "ask": 6},
         "lowPrice": {"bid": 0, "ask": 2}, "closePrice": {"bid": 2, "ask": 4}}]}
    (t, o, h, l, c), = parse_prices(data, "1d")
    assert dt.datetime.fromtimestamp(t, dt.timezone.utc).date() == dt.date(2026, 11, 23)
    assert (o, h, l, c) == (2, 5, 1, 3)
