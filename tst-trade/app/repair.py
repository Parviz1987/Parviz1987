"""Avtomatik təmir — icazəli addımlar kataloqu (owner 2026-11-26, plan step 4). The server repairs itself only with
the steps listed here, each with its trigger, its limit and a check afterwards; every step is written to ops_actions.
Nothing outside this catalogue is ever done automatically, and nothing at all while the owner's «Dayandır» switch is
pressed (ops.paused).

Catalogue:
- price_fallback: the main price stream is silent in open market hours (no price for 3 minutes, 3 checks in a row)
  -> the public gold-api.com prices for 30 minutes, then the main source again. At most 1 per 30 min and 4 a day.
- wal_checkpoint: SQLite's write journal (WAL) has grown past 300 MB -> a passive checkpoint (never deletes anything).
  At most 1 an hour.
- restart_engine: the engine's main loop has died -> started again. At most 3 an hour and 6 a day; then it stays
  stopped and the outside watcher reports it.

The same fault twice within 7 days opens a review (ops_reviews) that the owner closes in Admin; the third time within
7 days the step is no longer taken automatically (it waits for the owner)."""
from __future__ import annotations

import asyncio
import json
import os
import time

from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS ops_actions (ts REAL NOT NULL, action TEXT NOT NULL, fault TEXT NOT NULL, evidence TEXT,
  result TEXT, verified INTEGER);
CREATE INDEX IF NOT EXISTS ops_actions_ts ON ops_actions(ts);
CREATE TABLE IF NOT EXISTS ops_reviews (id INTEGER PRIMARY KEY, ts REAL NOT NULL, fault TEXT NOT NULL, count INTEGER,
  status TEXT NOT NULL DEFAULT 'açıq', closed_ts REAL, note TEXT);
"""
LIMITS = {"price_fallback": [(1800, 1), (86400, 4)], "wal_checkpoint": [(3600, 1)],
          "restart_engine": [(3600, 3), (86400, 6)]}
WEEK = 7 * 86400
FALLBACK_FOR = 1800
WAL_MAX = 300e6


def _ensure(db: DB) -> None:
    if not getattr(db, "_repair_ready", False):   # the schema once per database (executescript commits)
        db.script(SCHEMA)
        db._repair_ready = True


def allowed(db: DB, action: str, fault: str, now: float | None = None) -> tuple[bool, str]:
    """The guards before any step: the owner's switch, the step's limits, and the third repeat of a fault."""
    from . import ops
    _ensure(db)
    now = time.time() if now is None else now
    if ops.paused(db):
        return False, "sahib avtomatik təmiri dayandırıb"
    for span, n in LIMITS.get(action, [(3600, 1)]):
        done = db.execute("SELECT COUNT(*) n FROM ops_actions WHERE action=? AND ts > ?", (action, now - span)).fetchone()["n"]
        if done >= n:
            return False, f"limit: {n} dəfə / {round(span / 3600)} saat"
    # counted since the owner last closed a review of this fault: closing it is the owner's «go on»
    closed = db.execute("SELECT MAX(closed_ts) t FROM ops_reviews WHERE fault=? AND status='bağlanıb'",
                        (fault,)).fetchone()["t"] or 0
    rep = db.execute("SELECT COUNT(*) n FROM ops_actions WHERE fault=? AND ts > ?",
                     (fault, max(now - WEEK, closed))).fetchone()["n"]
    if rep >= 2:
        return False, "eyni nasazlıq 7 gündə 3-cü dəfədir: sahibin qərarını gözləyir"
    return True, ""


def record(db: DB, action: str, fault: str, evidence: str, result: str, now: float | None = None) -> None:
    _ensure(db)
    now = time.time() if now is None else now
    db.execute("INSERT INTO ops_actions VALUES(?,?,?,?,?,NULL)", (now, action, fault, evidence[:300], result[:200]))
    closed = db.execute("SELECT MAX(closed_ts) t FROM ops_reviews WHERE fault=? AND status='bağlanıb'",
                        (fault,)).fetchone()["t"] or 0
    n = db.execute("SELECT COUNT(*) n FROM ops_actions WHERE fault=? AND ts > ?",
                   (fault, max(now - WEEK, closed))).fetchone()["n"]
    if n >= 2 and not db.execute("SELECT 1 FROM ops_reviews WHERE fault=? AND status='açıq'", (fault,)).fetchone():
        db.execute("INSERT INTO ops_reviews(ts, fault, count, status) VALUES(?,?,?,'açıq')", (now, fault, n))


def close_review(db: DB, rid: int, note: str) -> bool:
    _ensure(db)
    return db.execute("UPDATE ops_reviews SET status='bağlanıb', closed_ts=?, note=? WHERE id=? AND status='açıq'",
                      (time.time(), note[:300], rid)).rowcount > 0


# ---------- the steps ----------
class Repairer:
    def __init__(self, db: DB, engine):
        self.db, self.engine = db, engine
        self.silent = 0
        self.started = time.time()

    async def check(self, now: float | None = None) -> list[str]:
        """Every minute. Returns the steps taken (for the log)."""
        now = time.time() if now is None else now
        done = []
        for step in (self._price, self._engine_alive):
            try:
                r = step(now)
                if r:
                    done.append(r)
            except Exception as e:          # a repair step never breaks the panel
                done.append(f"{step.__name__}: {type(e).__name__}")
        try:
            r = await self._wal(now)
            if r:
                done.append(r)
        except Exception as e:
            done.append(f"_wal: {type(e).__name__}")
        return done

    def _price(self, now: float) -> str | None:
        from .engine import market_open
        from .heartbeat import early_close, holiday
        eng = self.engine
        if eng.fallback_until and now >= eng.fallback_until:
            # 30 minutes over: chosen_provider() is the main source again by itself (the provider is rebuilt at the
            # next poll, never in the middle of one); the return is not a new fault and is not counted
            eng.fallback_until = 0.0
            return "price_fallback: əsas mənbəyə qayıtdı"
        if eng.chosen_provider() in ("goldapi", "demo") or eng.fallback_until:
            self.silent = 0
            return None
        if (not market_open(now) or not market_open(now - 900) or holiday(now) or holiday(now + 6 * 3600)
                or early_close(now) or now - self.started < 600):
            self.silent = 0
            return None
        age = now - (eng.last_ok or self.started)
        self.silent = self.silent + 1 if age > 180 else 0
        if self.silent < 3:
            return None
        ok, why = allowed(self.db, "price_fallback", "price:primary_offline", now)
        if not ok:
            return None
        eng.fallback_until = now + FALLBACK_FOR     # chosen_provider() changes; rebuilt at the next poll
        self.silent = 0
        record(self.db, "price_fallback", "price:primary_offline", f"əsas mənbədən {round(age)} san qiymət yoxdur",
               "30 dəqiqəlik gold-api.com", now)
        return "price_fallback: gold-api.com 30 dəqiqə"

    async def _wal(self, now: float) -> str | None:
        if self.db.path == ":memory:":
            return None
        wal = str(self.db.path) + "-wal"
        try:
            size = os.path.getsize(wal)
        except OSError:
            return None
        if size < WAL_MAX:
            return None
        ok, _ = allowed(self.db, "wal_checkpoint", "db:wal_big", now)
        if not ok:
            return None
        # in a worker thread (copying hundreds of MB must not freeze the panel); TRUNCATE gives the space back
        r = await asyncio.to_thread(lambda: self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())
        try:
            after = os.path.getsize(wal)
        except OSError:
            after = 0
        record(self.db, "wal_checkpoint", "db:wal_big", f"WAL {round(size / 1e6)} MB",
               f"sonra {round(after / 1e6)} MB ({'kiçildi' if after < WAL_MAX else 'kiçilmədi: oxuyan var'})", now)
        self.db.execute("UPDATE ops_actions SET verified=? WHERE action='wal_checkpoint' AND ts=?",
                        (int(after < WAL_MAX), now))
        return "wal_checkpoint"

    def _engine_alive(self, now: float) -> str | None:
        t = getattr(self.engine, "_task", None)
        if t is None or not t.done() or self.engine._stop.is_set():
            return None
        err = None if t.cancelled() else t.exception()
        ok, _ = allowed(self.db, "restart_engine", "engine:died", now)
        if not ok:
            return None
        self.engine.start()
        record(self.db, "restart_engine", "engine:died", f"{type(err).__name__ if err else 'dayandı'}", "yenidən başladı",
               now)
        return "restart_engine"


def view(db: DB) -> dict:
    _ensure(db)
    acts = [dict(r) for r in db.execute("SELECT ts, action, fault, evidence, result FROM ops_actions ORDER BY ts DESC "
                                        "LIMIT 20").fetchall()]
    revs = [dict(r) for r in db.execute("SELECT id, ts, fault, count, status, note FROM ops_reviews ORDER BY ts DESC "
                                        "LIMIT 20").fetchall()]
    return {"actions": acts, "reviews": revs,
            "open_reviews": sum(1 for r in revs if r["status"] == "açıq")}
