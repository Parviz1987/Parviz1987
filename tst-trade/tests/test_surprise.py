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


def test_hunter_needs_two_brains_to_agree(monkeypatch):
    import asyncio
    from app import brains
    from app.feeds import Feeds
    from app.hunter import Hunter
    from app.keys import KeyStore
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    Feeds(db, ks)
    ks.set("openai", {"key": "sk-test-1234"})
    rel = dt.datetime(2026, 11, 13, 13, 30, tzinfo=dt.timezone.utc).timestamp()
    db.execute("INSERT INTO events VALUES('e1', 'CPI m/m', 'USD', ?, 'High', '0.3%', '0.2%', NULL)", (rel,))
    answers = [[({"found": True, "actual": "0.5%", "source_url": "https://www.bls.gov/x"}, "openai"),
                ({"found": True, "actual": "0.4%", "source_url": "https://www.reuters.com/y"}, "anthropic")],
               [({"found": True, "actual": "0.5%", "source_url": "https://www.bls.gov/x"}, "openai"),
                ({"found": True, "actual": "0.5%", "source_url": "https://www.reuters.com/y"}, "anthropic")]]

    async def fake(*a, **k):
        return answers.pop(0)
    monkeypatch.setattr(brains, "run_both", fake)
    h = Hunter(db, ks)
    assert asyncio.run(h.tick(rel + 60)) == 0 and not h.due(rel + 60)        # too early: not asked
    assert asyncio.run(h.tick(rel + 150)) == 0                               # brains disagree: nothing used
    assert surprise.Lookup(db).items == []
    assert asyncio.run(h.tick(rel + 500)) == 1                               # second try: both say 0.5 %
    lk = surprise.Lookup(db)
    (item,) = lk.items
    assert item["gold"] == -1 and item["ts"] == rel + 500                    # visible only from when it was found
    assert lk.window(rel + 900, "15m") == [item] and not lk.window(rel + 400, "15m")
    assert len(h.recent()) == 2
