"""Watching the system from inside: an error journal and a read-only diagnostics report.

ErrorJournal is a logging handler: every ERROR (with its traceback) is stored once per kind, with a counter and the
first / last time, and every saved key is masked out before it is written. The report (/api/diag) is read-only and
holds no key, password or token: it is what an outside reviewer (the scheduled Claude check) reads."""
from __future__ import annotations

import hashlib
import logging
import json
import os
import time
import traceback

from . import brains, brainviews, candles, forecast, hypotheses, judge, learning, registry, signals
from . import feeds as feeds_mod
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
        db.script(SCHEMA)

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


def _pipeline(db: DB, keys, engine, feeds, jobs) -> list:
    from .pipeline import check
    try:
        return check(db, keys, engine, feeds, jobs)
    except Exception as e:   # the report must not fail because one check did
        return [{"stage": "Axın xəritəsi", "into": "", "status": "bad", "msg": f"yoxlama xətası: {e}", "n": None}]


def _shadow(db: DB) -> dict:
    """Success map in brief, for the monitor: per metal and horizon, each method's average result per trade after
    cost (fraction of the price), trades and proof status (history mode, cached 15 minutes)."""
    from . import simulator
    out = {}
    try:
        for sym in ("XAU", "XAG"):
            for h in ("1h", "4h", "1d", "1mo"):
                r = simulator.cached(db, sym, h)
                out[f"{sym}/{h}"] = {"buy_hold": r.get("buy_hold", {}).get("avg"),
                                     **{m: {"n": v["n"], "avg": round(v["avg"], 6), "status": v["status"]}
                                        for m, v in r["methods"].items() if v.get("n")}}
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


_SLOW: dict = {}


def _slow(key: str, fn, ttl: float = 600):
    """Heavy sections (they read weeks of forecasts and candles) are computed at most every 10 minutes: a diagnostics
    request must never keep the database busy long enough to slow the site."""
    hit = _SLOW.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    out = fn()
    _SLOW[key] = (time.time(), out)
    return out


def _security(db: DB) -> dict:
    from .security import Guard
    return Guard(db).summary()


def _memory() -> dict:
    """The process's memory now and at its peak, and what the machine has left (Linux /proc; MB)."""
    out = {}
    try:
        for line in open("/proc/self/status"):
            if line.startswith(("VmRSS:", "VmHWM:")):
                out[line.split(":")[0]] = round(int(line.split()[1]) / 1024)
        for line in open("/proc/meminfo"):
            if line.startswith(("MemTotal:", "MemAvailable:", "SwapFree:")):
                out[line.split(":")[0]] = round(int(line.split()[1]) / 1024)
    except OSError:
        pass
    return out


def _bid_ask(engine, sym: str):
    q = getattr(engine.provider, "latest", {}).get(sym)
    return [q.bid, q.ask] if q is not None and q.bid is not None else None


def report(db: DB, keys, engine, feeds, jobs, version: str | None) -> dict:
    now = time.time()
    db.script(SCHEMA)
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
                for r in judge.stats(db, sym, h, mode, ttl=60):
                    if r["method"] in forecast.BASELINES and r["method"] != "up":
                        continue
                    judging.setdefault(f"{sym}/{h}/{mode}", []).append(
                        {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()
                         if k in ("method", "n", "nh", "hit_rate", "bar", "p", "bss", "cover50", "cover80", "status")})
    open_fc = db.execute("SELECT COUNT(*) FROM forecasts WHERE scored_ts IS NULL").fetchone()[0]
    open_by = {f"{r['horizon']}/{r['mode']}": {"n": r["n"], "oldest_target_age_h": round((now - r["t"]) / 3600, 1)}
               for r in db.execute("SELECT horizon, mode, COUNT(*) n, MIN(target_t) t FROM forecasts "
                                   "WHERE scored_ts IS NULL GROUP BY horizon, mode").fetchall()}
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
        "sources": {k: feeds.health(k) for k in feeds_mod.SOURCE_IDS},
        "keys": key_state,
        "brains": [{**{k: b[k] for k in ("id", "name", "state", "in_use", "spent", "last_call")},
                    "config": {k: v for k, v in b["config"].items()}} for b in brains.view(db, keys)],
        "brain_jobs": {k: jobs.state(k) for k in ("scout", "hunter", "reader", "strategist")},
        "hunter": jobs.hunter.recent(5),
        "history": engine.history_state,
        "memory_mb": _memory(),
        "shadow_trading": _shadow(db),
        "pipeline": _pipeline(db, keys, engine, feeds, jobs),
        "brain_score": _slow("brain_score", lambda: brainviews.score(db, time.time())),
        "hypotheses": _slow("hypotheses", lambda: hypotheses.evaluate(db)),
        "learning": {"ab_lessons": _slow("ab", lambda: learning.ab_report(db)), "lessons": learning.active_lessons(db),
                     "sleep": json.loads(db.get("sleep:last") or "null"), "calib": json.loads(db.get("calib") or "null"),
                     "nerve": json.loads(db.get("nerve:state") or "null"), "backup": json.loads(db.get("backup:last") or "null")},
        "weights": {f"{s}/{h}": engine.weights(s, h, time.time()) for s in candles.METALS
                    for h in forecast.HORIZONS} if engine is not None else {},
        "signals": {"recent": signals.recent(db, 10),
                    "alarms_today": db.get("alarm:count")},
        "security": _security(db),
        "related": {**json.loads(db.get("related:epics") or "{}"),
                    "quotes": {c: engine.status(c, now) for c in json.loads(db.get("related:epics") or "{}").get("epics", {})}},
        "calendar_actuals": db.execute("SELECT COUNT(*) n, COUNT(actual) a FROM events WHERE ts < ?", (now,)).fetchone()[:],
        # where the methods miss (history), for the on-duty monitor's proposals
        "where": {f"{sym}/{h}": judge.where(db, sym, h, "history") for sym in ("XAU", "XAG") for h in ("1h", "4h", "1d")},
        "forecasts_open": open_fc,
        "forecasts_open_by": open_by,
        "judge": judging,
        "errors": errors,
        "db_bytes": os.path.getsize(db_path) if db_path and os.path.exists(db_path) else None,
    }
