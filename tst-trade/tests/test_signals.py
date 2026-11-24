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


def test_brain_jobs_run_while_the_main_loop_is_busy():
    """An alarm must not wait behind a slow history reload: the brains have their own loop."""
    from app.engine import Engine

    class Jobs:
        n = 0

        async def tick(self):
            Jobs.n += 1

    db = DB(":memory:")
    eng = Engine(db, KeyStore(db, "s" * 64), "demo", 15, None, Jobs())

    async def slow_backfill(force=False):
        await asyncio.sleep(0.3)
        eng._stop.set()
        return {}
    eng.backfill = slow_backfill
    asyncio.run(eng.run())
    assert Jobs.n >= 1


def test_moves_alone_use_only_their_share_of_alarms(monkeypatch):
    db, jobs = _jobs()
    jobs.next_strategist = jobs.next_reader = jobs.next_scout = NOW + 10 ** 6
    signals.ensure(db)
    calls = []

    async def fake(db_, keys, slot, system, user, schema, max_tokens=2000, search=False):
        calls.append(user)
        return {"summary": "s", "watch": [], "metals": []}, "test · m"
    monkeypatch.setattr(brains, "run", fake)
    for i in range(6):
        t = NOW + i * 1000
        signals.emit(db, f"m{i}", "move", "Qızıl tərpəndi", 3, "XAU", t)     # strong: passes the 1-hour habituation
        asyncio.run(jobs.tick(t))
    assert len(calls) == signals.MOVE_ALARMS_PER_DAY
    signals.emit(db, "n1", "news", "War", 3, "XAU", NOW + 7000)
    asyncio.run(jobs.tick(NOW + 7000))
    assert len(calls) == signals.MOVE_ALARMS_PER_DAY + 1          # a strong headline still gets its alarm


def test_attention_filter_lets_a_repeat_go_quietly():
    db, _ = _jobs()
    signals.ensure(db)
    signals.emit(db, "f1", "flow", "Qızıl: xəbər axını", 2, "XAU", NOW)
    signals.mark(db, [r["id"] for r in signals.pending(db, NOW)], NOW)
    signals.emit(db, "f2", "flow", "Qızıl: yenə eyni hekayə", 2, "XAU", NOW + 600)
    assert signals.pending(db, NOW + 600) == []                      # habituated: no new alarm within the hour
    signals.emit(db, "n1", "news", "War", 3, "XAU", NOW + 700)
    assert [s["kind"] for s in signals.pending(db, NOW + 700)] == ["news"]


def test_reflex_closes_a_metal_at_once_and_reopens_after_the_hold():
    from app.nerve import REFLEX_HOLD, Reflex
    r = Reflex()
    r.feel("XAU", NOW, 4000.0)
    r.feel("XAU", NOW + 30, 4000.0 * 1.004)                          # +0.4 % in 30 s
    assert r.closed("XAU", NOW + 31).startswith("refleks")
    assert r.closed("XAU", NOW + 31 + REFLEX_HOLD) is None


def test_prediction_error_alarm_when_price_leaves_our_range():
    from app import nerve
    from app.engine import Engine
    from app.judge import insert
    db = DB(":memory:")
    Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    insert(db, [("XAU", "1h", "rw", "live", NOW - 600, NOW + 3000, 100.0, 0.5, 99.5, 100.5, 99.0, 101.0, "b")])
    candles.store_history(db, "XAU", "1m", [(NOW // 60 * 60 - 60, 102.0, 102.0, 102.0, 102.0)])
    st = nerve.update(db, NOW)
    assert st["mod"]["surprise"]["XAU"] == 2.0 and st["state"] == "DİQQƏT"
    assert [s["kind"] for s in signals.pending(db, NOW)] == ["band"]
