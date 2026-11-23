import datetime as dt

from app import forecast, surprise
from app.db import DB


def _db():
    db = DB(":memory:")
    db.conn.executescript(surprise.SCHEMA)
    return db


def test_parse_fmp_and_direction_rules():
    rows = surprise.parse_fmp([
        {"date": "2026-11-13 13:30:00", "country": "US", "event": "CPI (YoY) (Oct)", "currency": "USD",
         "previous": 3.0, "estimate": 3.1, "actual": 3.3, "impact": "High"},
        {"date": "2026-11-13 13:30:00", "country": "US", "event": "Initial Jobless Claims", "estimate": "220K",
         "actual": "250K", "impact": "Medium"},
        {"date": "2026-11-13 09:00:00", "country": "DE", "event": "German CPI", "estimate": 1, "actual": 2}])
    assert len(rows) == 2
    assert rows[0]["ts"] == dt.datetime(2026, 11, 13, 13, 30, tzinfo=dt.timezone.utc).timestamp()
    assert rows[1]["estimate"] == 220000 and rows[1]["actual"] == 250000
    cpi, claims = (surprise.surprise_of(r) for r in rows)
    assert cpi["gold"] == -1 and cpi["weight"] == 1.0            # hot inflation: bad for gold
    assert claims["gold"] == +1 and claims["weight"] == 0.5      # more jobless claims: good for gold
    assert surprise.gold_direction("Baker Hughes Rig Count") == 0
    try:
        surprise.parse_fmp({"Error Message": "Special Endpoint"})
        raise AssertionError("must fail")
    except ValueError as e:
        assert "Special" in str(e)


def test_window_sees_only_past_releases():
    db = _db()
    t = dt.datetime(2026, 11, 13, 13, 30, tzinfo=dt.timezone.utc).timestamp()
    surprise.store(db, surprise.parse_fmp([{"date": "2026-11-13 13:30:00", "country": "US", "event": "CPI (YoY)",
                                            "estimate": 3.1, "actual": 3.3, "impact": "High"}]))
    lk = surprise.Lookup(db)
    assert lk.window(t, "1h") == []                    # the candle starting at the release itself: not yet seen
    assert len(lk.window(t + 3600, "1h")) == 1         # the next hour's forecast sees it
    assert lk.window(t + 3 * 3600, "1h") == []         # out of the one-hour window
    assert lk.window(t - 86400 * 30, "1h") is None     # before the data starts: no view, not "no news"
    up = [{"o": 100 + i, "h": 100.5 + i, "l": 99.5 + i, "c": 100 + i} for i in range(60)]
    m = forecast.build(up, "1h", releases=lk.window(t + 3600, "1h"))["methods"]["surprise"]
    assert m["p_up"] < 0.5 and "CPI" in m["basis"]
    assert "surprise" not in forecast.build(up, "1w")["methods"]
