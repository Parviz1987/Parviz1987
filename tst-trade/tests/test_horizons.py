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
    for i in range(40):
        d = (dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat()
        db.execute("INSERT INTO macro VALUES('DFII10', ?, ?)", (d, 2.0 - 0.01 * i))
        db.execute("INSERT INTO macro VALUES('DTWEXBGS', ?, ?)", (d, 120.0))
    t = int(dt.datetime(2026, 1, 25, tzinfo=dt.timezone.utc).timestamp())
    lk = MacroLookup(db)
    m = lk.at(t)
    assert abs(m["dfii10"] - (-0.05)) < 1e-9 and m["dollar"] == 0
    # published lags: the candle of 25 Jan (issued 24 Jan 22:00 UTC) may use DFII10 up to 23 Jan only
    db.execute("UPDATE macro SET v=99 WHERE series='DFII10' AND d='2026-01-24'")
    assert lk.at(t) == MacroLookup(db).at(t)


def test_capital_history_parse_moves_sunday_session_to_monday():
    data = {"prices": [
        {"snapshotTimeUTC": "2026-11-22T22:00:00", "openPrice": {"bid": 1, "ask": 3}, "highPrice": {"bid": 4, "ask": 6},
         "lowPrice": {"bid": 0, "ask": 2}, "closePrice": {"bid": 2, "ask": 4}}]}
    (t, o, h, l, c), = parse_prices(data, "1d")
    assert dt.datetime.fromtimestamp(t, dt.timezone.utc).date() == dt.date(2026, 11, 23)
    assert (o, h, l, c) == (2, 5, 1, 3)


def test_session_method_uses_same_hour_only():
    t0 = int(dt.datetime(2026, 1, 5, tzinfo=dt.timezone.utc).timestamp())
    cands = []
    for i in range(24 * 40):
        t = t0 + i * 3600
        up = (t // 3600) % 24 == 3               # 03:00 UTC candles always rise, the others fall
        cands.append({"t": t, "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5 if up else 99.5})
    # next candle 03:00 -> up view; next 04:00 -> down view
    at3 = [c for c in cands if c["t"] < t0 + 30 * 86400 + 3 * 3600]
    p3 = forecast.build(at3, "1h")["methods"]["session"]["p_up"]
    at4 = [c for c in cands if c["t"] < t0 + 30 * 86400 + 4 * 3600]
    p4 = forecast.build(at4, "1h")["methods"]["session"]["p_up"]
    assert p3 > 0.6 and p4 < 0.4
    assert "session" not in forecast.build(at3, "1d")["methods"]


def test_no_weekend_daily_forecasts_and_monday_follows_friday():
    db = DB(":memory:")
    eng = Engine(db, KeyStore(db, SECRET), "demo", 15)
    rows = _daily(db, 60)
    fri = rows[-1][0]
    while dt.datetime.fromtimestamp(fri, dt.timezone.utc).weekday() != 4:
        fri -= 86400
    db.execute("DELETE FROM candles WHERE tf='1d' AND t>?", (fri,))
    for day in (1, 2):                                 # Saturday and Sunday noon: nothing issued
        assert eng.issue_due(fri + day * 86400 + 43200) == 0
    n = eng.issue_due(fri + 3 * 86400 + 3600)          # Monday 01:00 UTC: forecasts for Monday's candle
    assert n > 0
    assert db.execute("SELECT COUNT(DISTINCT issued_t) FROM forecasts WHERE horizon='1d'").fetchone()[0] == 1


def test_weekend_history_bars_are_not_daily_candles():
    db = DB(":memory:")
    sat = int(dt.datetime(2026, 11, 21, tzinfo=dt.timezone.utc).timestamp())
    fri = sat - 86400
    candles.store_history(db, "XAU", "1d", [(fri, 1, 1, 1, 1), (sat, 1, 1, 1, 1), (sat + 86400, 1, 1, 1, 1)])
    assert [c["t"] for c in candles.get(db, "XAU", "1d")] == [fri]


def test_selective_consensus_counts_families_not_methods():
    def m(**kw):
        return {k: {"p_up": v} for k, v in kw.items()}
    calm = [0.001 * (1 if i % 2 else -1) for i in range(200)]
    # three trend-family methods up, one revert method down: one idea against another -> no view
    out = forecast.selective_consensus(m(momentum=0.6, trend=0.6, breakout=0.6, rsi=0.4), calm, 0.001, False)
    assert out["p_up"] == 0.5 and "razı deyil" in out["basis"]
    # two independent families up, nobody against -> a direction
    out = forecast.selective_consensus(m(trend=0.6, dollar=0.58), calm, 0.001, False)
    assert out["p_up"] > 0.5 and "2 müstəqil ailə" in out["basis"]
    # one family only (however many methods) -> no view
    assert forecast.selective_consensus(m(momentum=0.6, trend=0.65), calm, 0.001, False)["p_up"] == 0.5
    # near a high-impact release, or in a wild market -> no view
    assert forecast.selective_consensus(m(trend=0.6, dollar=0.58), calm, 0.001, True)["p_up"] == 0.5
    assert forecast.selective_consensus(m(trend=0.6, dollar=0.58), calm, 0.01, False)["p_up"] == 0.5


def test_pullback_in_an_up_trend():
    cands = [{"o": 100 + i * 0.5, "h": 100.6 + i * 0.5, "l": 99.8 + i * 0.5, "c": 100.5 + i * 0.5} for i in range(80)]
    top = cands[-1]["c"]
    # a dip to around the EMA 20 (about 5 points below the top) and a green candle back up
    cands += [{"o": top, "h": top, "l": top - 6, "c": top - 5}, {"o": top - 5, "h": top - 2, "l": top - 5.5, "c": top - 2}]
    p, basis = forecast.pullback_view(cands, 0.002)
    assert p == forecast.SIGNAL_P and "EMA 20" in basis
    flat = [{"o": 100, "h": 100.5, "l": 99.5, "c": 100 + (0.2 if i % 2 else -0.2)} for i in range(80)]
    assert forecast.pullback_view(flat, 0.002)[0] == 0.5

def test_every_method_has_a_passport():
    for m in forecast.METHODS:
        p = forecast.PASSPORT[m]
        assert p["why"] and p["expect"] and p["else"], m
