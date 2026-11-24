from app import forecast
from app.brainjobs import BrainJobs
from app.brainviews import Lookup
from app.db import DB
from app.feeds import Feeds
from app.keys import KeyStore


def test_news_mood_and_strategist_lean_use_only_the_past():
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    BrainJobs(db, ks, Feeds(db, ks))
    t = 1_800_000_000
    for i, (d, s) in enumerate([("up", 2), ("up", 3), ("down", 1)]):
        db.execute("INSERT INTO news_ai VALUES(?,?,?,?,?,?,?)", (f"n{i}", t - 1800 + i * 60, "x", "XAU", d, s, "b"))
    db.execute("INSERT INTO news_ai VALUES('late', ?, 'x', 'XAU', 'down', 3, 'b')", (t + 30,))   # after the forecast
    db.execute("INSERT INTO brain_views(ts, source, metal, lean, note) VALUES(?, 'strateq', 'XAU', -1, 'b')",
               (t - 600,))    # an old lean-only note: still counts for 4 h and 1 day
    v = Lookup(db).views("XAU", t, "4h")
    assert v["news"][0] > 0.5 and "+4" in v["news"][1]
    assert v["strateq"][0] == 0.4
    assert "strateq" not in Lookup(db).views("XAU", t, "15m")
    assert Lookup(db).views("XAG", t, "1h")["news"][0] == 0.5
    up = [{"o": 100 + i, "h": 100.5 + i, "l": 99.5 + i, "c": 100 + i} for i in range(60)]
    m = forecast.build(up, "4h", views=v)["methods"]
    assert m["news"]["p_up"] > 0.5 and m["strateq"]["p_up"] == 0.4
    assert "news" not in forecast.build(up, "1w")["methods"]


def test_strategist_probability_per_horizon():
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    BrainJobs(db, ks, Feeds(db, ks))
    from app import brainviews
    brainviews.ensure(db)
    t = 1_800_000_000
    db.executemany("INSERT INTO brain_views(ts, source, metal, lean, note, horizon, p) VALUES(?,?,?,?,?,?,?)",
                   [(t - 900, "strateq", "XAU", 1, "b", "1h", 0.9), (t - 900, "strateq", "XAU", 0, "b", "4h", 0.5),
                    (t - 30, "strateq", "XAU", -1, "late", "1h", 0.1)])       # written after the issue: unseen
    lk = Lookup(db)
    assert lk.views("XAU", t, "1h")["strateq"][0] == 0.7          # capped at 0.7
    assert lk.views("XAU", t, "4h")["strateq"][0] == 0.5
    assert lk.views("XAU", t + 3 * 3600, "1h")["strateq"][0] == 0.5   # an hour-old view is too old for 1 h
    assert "strateq" in forecast.methods_for("1h")


def test_strategist_saves_its_forecast_and_gets_price_moves(monkeypatch):
    import asyncio
    from app import brains, candles
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    jobs = BrainJobs(db, ks, Feeds(db, ks))
    now = 1_800_000_000
    for i in range(40):
        candles.store_history(db, "XAU", "15m", [((now // 900 - 40 + i) * 900, 100 + i, 101 + i, 99 + i, 100 + i)])
    facts = jobs.facts(now)
    assert '"XAU": {"1h"' in facts and "moves_pct" in facts
    seen = {}

    async def fake(db_, keys, slot, system, user, schema, max_tokens=2000, search=False):
        seen["user"] = user
        return {"summary": "s", "watch": [], "metals": [
            {"symbol": "XAU", "text": "t", "p1h": 0.62, "p4h": 0.55, "p1d": 0.5, "why": "dollar zəifləyir"},
            {"symbol": "BTC", "text": "t", "p1h": 0.9, "p4h": 0.9, "p1d": 0.9, "why": "x"}]}, "test · m"
    monkeypatch.setattr(brains, "run", fake)
    assert asyncio.run(jobs.strategist(now))
    rows = db.execute("SELECT metal, horizon, p FROM brain_views WHERE horizon IS NOT NULL ORDER BY horizon").fetchall()
    assert [(r["metal"], r["horizon"], r["p"]) for r in rows] == [("XAU", "1d", 0.5), ("XAU", "1h", 0.62),
                                                                    ("XAU", "4h", 0.55)]
    assert Lookup(db).views("XAU", now + 600, "1h")["strateq"][0] == 0.62
