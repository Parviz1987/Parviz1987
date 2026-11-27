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

from . import brains, brainviews, candles, forecast, hypotheses, impulse, judge, learning, registry, signals
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


def _calls(db: DB, now: float | None = None, hours: int = 12) -> dict:
    """Who said what in the last hours (owner 2026-11-27: «which analysts said gold would rise?»): per metal, horizon
    (1 h, 4 h, 1 day) and method, the live forecasts ISSUED in the window that took a side (up above 0.505, down
    below 0.495), the average probability of up, and of those already checked how many came true. A method without a
    side in the window is left out. Read only; uses the recent-forecasts index."""
    now = time.time() if now is None else now
    start = int(now - hours * 3600)
    out: dict = {"from": start, "hours": hours}
    for sym in ("XAU", "XAG", "XPT", "XPD"):
        per: dict = {}
        for r in db.execute("SELECT horizon, method, p_up, hit, scored_ts FROM forecasts WHERE symbol=? AND mode='live' "
                            "AND target_t>=? AND issued_t>=? AND horizon IN ('1h','4h','1d')", (sym, start, start)):
            p = r["p_up"]
            if p is None or 0.495 <= p <= 0.505:
                continue
            c = per.setdefault(r["horizon"], {}).setdefault(r["method"], {"up": 0, "down": 0, "p_sum": 0.0, "scored": 0, "right": 0})
            c["up" if p > 0.5 else "down"] += 1
            c["p_sum"] += p
            if r["scored_ts"] is not None and r["hit"] is not None:
                c["scored"] += 1
                c["right"] += int(r["hit"])
        for h in per.values():
            for c in h.values():
                c["p_up_avg"] = round(c.pop("p_sum") / (c["up"] + c["down"]), 3)
        out[sym] = per
    return out


def _scoreboard(db: DB) -> dict:
    """Yesterday and the last 7 days, all four metals: who was right on which horizon (static/results.js shows the
    same per period on the site). For the duty check's daily note."""
    from . import scoreboard
    return {p: scoreboard.board(db, "ALL", p) for p in ("yesterday", "7d")}


def _rules(db: DB) -> dict:
    """Bilik kitabı rules: the Judge's record per rule and timeframe (next candle and stop + target), and replay state."""
    from . import rules
    rec = rules.records(db)
    ver = {k: db.get(f"rules:ver:{s}:{tf}") for s in ("XAU", "XAG", "XPT", "XPD") for tf in rules.TFS
           for k in (f"{s}:{tf}",)}
    return {"bar": rec.get("bar"), "version": rules.RULES_VER, "replayed": ver,
            "rules": {r: {tf: {k: x.get(k) for k in ("n", "hit_rate", "net_avg", "status", "rr", "by_metal", "by_adx")} for tf, x in tfs.items()}
                      for r, tfs in rec.get("rules", {}).items()}}


def _tables(db: DB) -> list[dict]:
    """Where the database's size is: megabytes per table and index (sqlite's dbstat), biggest first; rows from the
    largest rowid (instant). Computed at most every 6 hours (dbstat reads the whole file)."""
    sizes = {}
    try:
        sizes = {r["name"]: r["b"] for r in db.execute("SELECT name, SUM(pgsize) b FROM dbstat GROUP BY name").fetchall()}
    except Exception:
        pass
    out = []
    for r in db.execute("SELECT name, type, tbl_name FROM sqlite_master WHERE type IN ('table', 'index')").fetchall():
        rows = None
        if r["type"] == "table":
            try:
                rows = db.execute(f'SELECT MAX(rowid) n FROM "{r["name"]}"').fetchone()["n"]
            except Exception:
                rows = None
        out.append({"name": r["name"], "type": r["type"], "table": r["tbl_name"],
                    "mb": round(sizes.get(r["name"], 0) / 1e6, 1), "rows": rows})
    return sorted(out, key=lambda x: -x["mb"])[:25]


def _forecast_rows(db: DB) -> list[dict]:
    """The forecast archive per method and mode (history = the replay, live = issued in real time), biggest first,
    with whether the method is still used — the base for any clean-up decision (owner decides)."""
    from . import forecast
    rows = db.execute("SELECT method, mode, COUNT(*) n FROM forecasts GROUP BY method, mode").fetchall()
    return sorted(({"method": r["method"], "mode": r["mode"], "n": r["n"],
                    "retired": r["method"] in getattr(forecast, "RETIRED", ()),
                    "used": r["method"] in forecast.METHODS} for r in rows), key=lambda x: -x["n"])


def _eventlib(db: DB) -> dict:
    try:
        from . import eventlib
        v = eventlib.view(db, "XAU")
        return {"state": v.get("state"), "xau_table": v.get("table", [])[:30], "last": v.get("last")}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _news_debug(db: DB) -> dict:
    try:
        from . import newsblock
        return newsblock.debug(db)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _autojudge(db: DB) -> dict | None:
    """The owner's policy: every method's score 0-100 and its ladder step (off / shadow / small / full paper share)."""
    try:
        from . import autojudge
        return autojudge.view(db)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _blockaudit(db: DB) -> dict | None:
    """Plan phase E: per block — inputs, rule firings, voice views, the Judge, its value, links; plain verdict."""
    try:
        from . import blockaudit
        v = blockaudit.view(db)
        return v and {"computed": v.get("computed"), "blocks": [{k: b.get(k) for k in (
            "id", "verdict", "why", "sources", "rules", "views_7d", "judge_best", "value_bss_drop", "state_dependent",
            "feeds", "labels")} for b in v.get("blocks", [])]}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _autopsy(db: DB) -> dict | None:
    """Plan step 11: why the headline forecasts missed (monthly; causes, slices, who misled, four boxes)."""
    try:
        from . import autopsy
        v = autopsy.view(db)
        return v and {"computed": v.get("computed"), "totals": v.get("totals"), "hints": v.get("hints"),
                      "desks": {k: {x: d.get(x) for x in ("n", "miss_rate", "causes", "boxes", "range_drift")}
                                for k, d in (v.get("desks") or {}).items()}}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _aci(db: DB) -> dict | None:
    """Plan step 9: the 80 % range with the adaptive correction, replayed on the past (shadow)."""
    try:
        from . import aci
        v = aci.view(db)
        return v and {"computed": v.get("computed"), "summary": v.get("summary"), "desks": v.get("desks")}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _experiments(db: DB) -> dict | None:
    """Shadow tests of the owner's block decisions (fundamental 3-year window, festival volatility)."""
    try:
        from . import shadowtests
        return shadowtests.view(db)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _ops(db: DB) -> dict:
    """The owner's «stop automatic repair» switch: while it is on, the duty check only reads and reports."""
    from . import ops, repair
    return {**ops.state(db), "repair": repair.view(db)}


def _router(db: DB) -> dict:
    """The brain router: models switched off and why, cooling down, proposals waiting for the owner, fallback rate."""
    try:
        from . import llmrouter
        return llmrouter.view(db)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _heartbeat(db: DB) -> dict | None:
    """The outside watcher: is it set up, and each check's last signal (never the ping addresses)."""
    try:
        from . import heartbeat
        h = heartbeat.HEART
        return h.view() if h is not None else {"note": "işləmir (test rejimi)"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _conductor(db: DB) -> dict | None:
    """The conductor's evidence: does each voice do better in some market states (stored once a day)."""
    try:
        from . import conductor
        sh = conductor.shadow_view(db) or {}
        return {"audit": conductor.audit_view(db),
                "shadow": {"computed": sh.get("computed"), "seconds": sh.get("seconds"), "params": sh.get("params"),
                           "desks": sh.get("desks")}}
    except Exception as e:          # the diagnostics never fail on one section
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _agents(db: DB) -> dict:
    """The data agents: each one's last confirmed figure and last attempt, and the last calls of their two brains
    (provider, model, ok, error) — whether each company's search really answers."""
    from . import reporter
    try:
        calls = [dict(r) for r in db.execute("SELECT ts, provider, model, ok, error FROM brain_calls WHERE slot='reporter' "
                                             "ORDER BY ts DESC LIMIT 8").fetchall()]
    except Exception:
        calls = []
    from . import llm
    return {"agents": [{k: a[k] for k in ("id", "value", "period", "last_ok", "last_note", "last_ts", "sources")}
                       for a in reporter.agents_view(db)], "calls": calls, "router": _router(db)}


def _update_log(db_path: str) -> list[str]:
    """The auto-update's own lines (deploy/update.sh writes data/update.log): updated, rolled back, slow start."""
    try:
        from pathlib import Path
        return Path(db_path).parent.joinpath("update.log").read_text().splitlines()[-15:]
    except (OSError, TypeError):
        return []


_SEALER: list = []          # the session secret, set by main (only to tell whether 2FA is on; never reported)


def _security(db: DB) -> dict:
    """The counts and alerts; for the failed logins of the last day only the PLACE (city, country), never the address:
    the outside reviewer must not see anyone's IP."""
    from . import geo
    from .security import Guard
    out = Guard(db).summary()
    places: dict[str, int] = {}
    for r in db.execute("SELECT ip FROM sec_events WHERE kind IN ('login_fail', 'login_blocked', 'diag_bad_token') "
                        "AND ts > ?", (time.time() - 86400,)).fetchall():
        k = geo.label(geo.place(r["ip"], db.path)) if r["ip"] else "—"
        places[k] = places.get(k, 0) + 1
    out["fail_places"] = places
    from . import totp
    out["two_factor"] = totp.enabled(db, _SEALER[0]) if _SEALER else None
    for a in out.get("alerts", []):
        a["place"] = geo.label(geo.place(a.get("ip"), db.path))
        a.pop("ip", None)
    return out


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


def _futures_now(db) -> dict:
    """The Databento download right now (not cached): bars and months stored per metal, running or not."""
    try:
        rows = db.execute("SELECT symbol, COUNT(*) n, MIN(t) a, MAX(t) b, COUNT(DISTINCT CAST(t / 2592000 AS INTEGER)) m "
                          "FROM fut_candles GROUP BY symbol").fetchall()
    except Exception:
        rows = []
    return {"running": db.get("futures:running"), "approved": json.loads(db.get("futures:approved") or "null"),
            "last": json.loads(db.get("futures:last") or "null"),
            "daily": {"approved": json.loads(db.get("futures:daily_approved") or "null"),
                      "try": json.loads(db.get("futures:daily_try") or "null"), "day": db.get("futures:daily_day")},
            "stored": {r["symbol"]: {"bars": r["n"], "months": r["m"], "from": time.strftime("%Y-%m-%d", time.gmtime(r["a"])),
                                     "to": time.strftime("%Y-%m-%d", time.gmtime(r["b"]))} for r in rows}}


def _plan_v3(db) -> dict:
    from . import cards, checker, futstudy, judge, newsevents
    last = cards.recent(db, None, 4)
    return {"swap": json.loads(db.get("swap_rates") or "null"),
            "cost_1d": {s: judge.cost_parts(s, "1d") for s in candles.METALS},
            "cards": {"last": last, "summary": cards.summary(db)},
            "checker": checker.report(db), "news_events": newsevents.day_counts(db),
            "focus": hypotheses.evaluate_focus(db), "alfred": json.loads(db.get("alfred:last") or "null"),
            "futstudy": futstudy.summary(db),
            "futures": {"quote": json.loads(db.get("futures:quote") or "null"),
                        "last": json.loads(db.get("futures:last") or "null"), "running": db.get("futures:running")}}


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
        "boots": json.loads(db.get("boot:log") or "[]")[-10:], "updates": _update_log(db_path),
        "tables": _slow("tables", lambda: _tables(db), 6 * 3600),
        "forecast_rows": _slow("forecast_rows", lambda: _forecast_rows(db), 6 * 3600),
        "calls_12h": _slow("calls_12h", lambda: _calls(db), 300),
        "scoreboard": _slow("scoreboard", lambda: _scoreboard(db), 900),
        "cleanup": json.loads(db.get("cleanup:retired_v1") or "null"),
        "vacuum": json.loads(db.get("cleanup:vacuum_v1") or "null"),
        "agents": _agents(db),
        "conductor": _conductor(db),
        "heartbeat": _heartbeat(db),
        "ops": _ops(db),
        "experiments": _experiments(db),
        "aci": _aci(db),
        "autopsy": _autopsy(db),
        "blocks_audit": _blockaudit(db),
        "judge_canary": json.loads(db.get("judge:canary") or "null"),
        "autojudge": _autojudge(db),
        "news_debug": _slow("news_debug", lambda: _news_debug(db), 600),
        "eventlib": _slow("eventlib", lambda: _eventlib(db), 600),
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
        "impulse_study": _slow("impulse", lambda: impulse.study(db), ttl=3600),
        # Plan v3 (Blocks 15-18): full cost, forecast cards, source checker, news events, focus targets, ALFRED
        "plan_v3": _slow("plan_v3", lambda: _plan_v3(db)),
        "futures_now": _futures_now(db),
        "rules": _slow("rules", lambda: _rules(db)),
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
