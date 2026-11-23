"""Watching the system from inside: an error journal and a read-only diagnostics report.

ErrorJournal is a logging handler: every ERROR (with its traceback) is stored once per kind, with a counter and the
first / last time, and every saved key is masked out before it is written. The report (/api/diag) is read-only and
holds no key, password or token: it is what an outside reviewer (the scheduled Claude check) reads."""
from __future__ import annotations

import hashlib
import logging
import os
import time
import traceback

from . import brains, candles, forecast, judge, registry
from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS errors (sig TEXT PRIMARY KEY, first_ts REAL, last_ts REAL, count INTEGER, logger TEXT,
  message TEXT, trace TEXT);
"""
STARTED = time.time()


class ErrorJournal(logging.Handler):
    def __init__(self, db: DB, secrets_fn):
        super().__init__(level=logging.ERROR)
        self.db = db
        self.secrets_fn = secrets_fn
        db.conn.executescript(SCHEMA)

    def _scrub(self, text: str) -> str:
        try:
            for s in self.secrets_fn():
                if s and len(s) >= 6:
                    text = text.replace(s, "***")
        except Exception:
            pass
        return text

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self._scrub(record.getMessage())[:500]
            trace = ""
            if record.exc_info:
                trace = self._scrub("".join(traceback.format_exception(*record.exc_info)))[-4000:]
            # Same place + same exception type = same kind of error (the message may hold changing numbers).
            where = f"{record.name}:{record.pathname}:{record.lineno}"
            kind = record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else ""
            sig = hashlib.sha1(f"{where}|{kind}".encode()).hexdigest()[:16]
            now = time.time()
            self.db.execute(
                "INSERT INTO errors(sig, first_ts, last_ts, count, logger, message, trace) VALUES(?,?,?,1,?,?,?) "
                "ON CONFLICT(sig) DO UPDATE SET last_ts=excluded.last_ts, count=count+1, message=excluded.message, "
                "trace=excluded.trace", (sig, now, now, record.name, msg, trace))
        except Exception:
            pass   # the journal must never break the app


def _bid_ask(engine, sym: str):
    q = getattr(engine.provider, "latest", {}).get(sym)
    return [q.bid, q.ask] if q is not None and q.bid is not None else None


def report(db: DB, keys, engine, feeds, jobs, version: str | None) -> dict:
    now = time.time()
    db.conn.executescript(SCHEMA)
    metals = {}
    for sym in candles.METALS:
        q = engine.quotes.get(sym)
        metals[sym] = {"status": engine.status(sym, now), "price": q["price"] if q else None,
                       "age_s": round(now - q["recv_ts"], 1) if q else None,
                       "recent": [round(r[0], 5) for r in db.execute(
                           "SELECT price FROM ticks WHERE symbol=? ORDER BY ts DESC LIMIT 8", (sym,)).fetchall()],
                       "ticks_hour": db.execute("SELECT COUNT(*) FROM ticks WHERE symbol=? AND ts>?",
                                                (sym, now - 3600)).fetchone()[0],
                       "bid_ask": _bid_ask(engine, sym),
                       "candles": {tf: db.execute("SELECT COUNT(*) FROM candles WHERE symbol=? AND tf=?",
                                                  (sym, tf)).fetchone()[0] for tf in candles.TF}}
    judging = {}
    for sym in candles.METALS:
        for h in forecast.HORIZONS:
            for mode in ("live", "history"):
                for r in judge.stats(db, sym, h, mode):
                    if r["method"] in forecast.BASELINES and r["method"] != "up":
                        continue
                    judging.setdefault(f"{sym}/{h}/{mode}", []).append(
                        {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()
                         if k in ("method", "n", "hit_rate", "bar", "p", "bss", "cover80", "status")})
    open_fc = db.execute("SELECT COUNT(*) FROM forecasts WHERE scored_ts IS NULL").fetchone()[0]
    key_state = {}
    for slot in registry.KEY_SLOTS:
        st = keys.status(slot["id"])
        key_state[slot["id"]] = {"saved": st["saved"], "unreadable": st["unreadable"],
                                 "check": st["check"], "feed_health": feeds.health(slot["id"])}
    db_path = db.conn.execute("PRAGMA database_list").fetchone()[2]
    errors = [dict(r) for r in db.execute("SELECT sig, first_ts, last_ts, count, logger, message, trace FROM errors "
                                          "ORDER BY last_ts DESC LIMIT 50").fetchall()]
    return {
        "version": version, "now": now, "uptime_s": round(now - STARTED),
        "provider": engine.provider_name, "provider_errors": engine.errors, "last_price_ok": engine.last_ok,
        "metals": metals,
        "sources": {k: feeds.health(k) for k in ("rss", "forexfactory", "fred", "cot")},
        "keys": key_state,
        "brains": [{**{k: b[k] for k in ("id", "name", "state", "in_use", "spent", "last_call")},
                    "config": {k: v for k, v in b["config"].items()}} for b in brains.view(db, keys)],
        "brain_jobs": {"reader": jobs.state("reader"), "strategist": jobs.state("strategist")},
        "history": engine.history_state,
        "forecasts_open": open_fc,
        "judge": judging,
        "errors": errors,
        "db_bytes": os.path.getsize(db_path) if db_path and os.path.exists(db_path) else None,
    }
