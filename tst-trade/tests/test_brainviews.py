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
               (t - 900,))    # an old lean-only note: still counts for 4 h and 1 day, from 10 minutes after its ts
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


def test_second_brain_answers_alone_and_is_stored_apart(monkeypatch):
    import asyncio
    from app import brains
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    ks.set("openai", {"key": "sk-test-1234"})
    jobs = BrainJobs(db, ks, Feeds(db, ks))
    slots = []

    async def fake(db_, keys, slot, system, user, schema, max_tokens=2000, search=False):
        slots.append(slot)
        assert "Strateq" not in user                       # the second brain never sees the first one's answer
        return {"summary": "s", "watch": [], "metals": [
            {"symbol": "XAG", "text": "t", "p1h": 0.4 if slot == "analyst2" else 0.6, "p4h": 0.5, "p1d": 0.5,
             "why": "x"}]}, "test · m"
    monkeypatch.setattr(brains, "run", fake)
    now = 1_800_000_000
    assert asyncio.run(jobs.strategist(now))
    assert slots == ["strategist", "analyst2"]
    v = Lookup(db).views("XAG", now + 600, "1h")
    assert v["strateq"][0] == 0.6 and v["brain2"][0] == 0.4


def test_report_card_starts_when_the_answer_arrived_and_beats_the_rival():
    """A view is scored from the price when its answer ARRIVED; the move before it belongs to the rival."""
    from app import brainviews, candles
    db = DB(":memory:")
    brainviews.ensure(db)
    t0 = 1_800_000_000 // 60 * 60
    # price jumps 100 -> 101 before the answer arrives, then drifts down to 100.5 over the next hour
    rows = [(t0 - 1800 + i * 60, 100.0, 100.0, 100.0, 100.0) for i in range(25)]
    rows += [(t0 - 300 + i * 60, 101.0, 101.0, 101.0, 101.0) for i in range(6)]
    rows += [(t0 + i * 60, 100.5, 100.5, 100.5, 100.5) for i in range(1, 62)]
    candles.store_history(db, "XAU", "1m", rows)
    db.execute("INSERT INTO brain_views(ts, source, metal, lean, note, horizon, p, known_ts) "
               "VALUES(?, 'strateq', 'XAU', 1, 'saatlıq', '1h', 0.7, ?)", (t0 - 400, t0))
    card = brainviews.score(db, t0 + 7200)[0]
    assert card["n"] == 1 and card["hit_rate"] == 0.0        # said up at 101: the price fell to 100.5
    assert card["net_avg"] < 0 and card["baseline_hit"] == 0.0
