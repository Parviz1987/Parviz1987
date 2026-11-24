"""The nerves: a strong headline, a confirmed figure or a sharp move wakes the Strategist at once, once per event."""
import asyncio

from app import brains, candles, signals
from app.brainjobs import BrainJobs
from app.db import DB
from app.feeds import Feeds
from app.keys import KeyStore

NOW = 1_800_000_000


def _jobs():
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    return db, BrainJobs(db, ks, Feeds(db, ks))


def test_strong_headline_and_flow_and_move_signal_once():
    db, _ = _jobs()
    signals.ensure(db)
    db.execute("INSERT INTO news(uid, source, url, title, ts, metals) VALUES('a','x','','War starts',?, 'XAU')", (NOW,))
    db.execute("INSERT INTO news_ai VALUES('a', ?, 'geopolitics', 'XAU', 'up', 3, 'b')", (NOW - 60,))
    db.execute("INSERT INTO news(uid, source, url, title, ts, metals) VALUES('b','x','','Fed cuts',?, 'XAU')", (NOW,))
    db.execute("INSERT INTO news_ai VALUES('b', ?, 'fed', 'XAU', 'up', 2, 'b')", (NOW - 30,))
    t0 = (NOW // 900 - 100) * 900
    rows = [(t0 + i * 900, 100.0, 100.1, 99.9, 100.0 + (0.02 if i % 2 else 0.0)) for i in range(99)]
    rows.append((t0 + 99 * 900, 100.0, 101.2, 100.0, 101.0))                      # a 1 % jump, usual move 0.02 %
    candles.store_history(db, "XAU", "15m", rows)
    assert signals.scan(db, NOW, ["XAU"]) == 3                                       # news, flow, move
    assert signals.scan(db, NOW + 5, ["XAU"]) == 0                                   # never twice
    kinds = sorted(s["kind"] for s in signals.pending(db, NOW + 5))
    assert kinds == ["flow", "move", "news"]


def test_alarm_runs_strategist_at_once_with_what_happened(monkeypatch):
    db, jobs = _jobs()
    jobs.next_strategist = NOW + 3000                    # the hourly run is far away
    jobs.next_reader = jobs.next_scout = NOW + 3000
    signals.ensure(db)
    signals.emit(db, "x1", "news", "Güclü xəbər (up): War starts", 3, "XAU", NOW - 10)
    seen = []

    async def fake(db_, keys, slot, system, user, schema, max_tokens=2000, search=False):
        seen.append(user)
        return {"summary": "s", "watch": [], "metals": [
            {"symbol": "XAU", "text": "t", "p1h": 0.6, "p4h": 0.6, "p1d": 0.55, "why": "müharibə"}]}, "test · m"
    monkeypatch.setattr(brains, "run", fake)
    asyncio.run(jobs.tick(NOW))
    assert len(seen) == 1 and "War starts" in seen[0]
    note = db.execute("SELECT note FROM brain_views WHERE horizon='1h'").fetchone()["note"]
    assert note.startswith("həyəcan")
    assert not signals.pending(db, NOW)                  # handled
    signals.emit(db, "x2", "news", "Another", 3, "XAU", NOW + 60)
    asyncio.run(jobs.tick(NOW + 60))
    assert len(seen) == 1                                 # 15-minute gap between alarms
