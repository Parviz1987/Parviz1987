"""Beyin keçidi (owner 2026-11-26, plan steps 6-7): every brain call goes through here, and here alone it is decided
what an error means. One retry layer only (the SDKs' own retries are off), so one request never silently becomes 10.

Per error class, one action (LiteLLM / OpenRouter / Anthropic / Google practice, verified 2026-11-26):
- nothing was sent (connection failed)            -> 1 retry, then the next approved model
- sent, no answer in time                           -> no retry (it may already cost money); 2 minutes cool-down
- 408 / 409                                         -> 1 retry
- 429 asking to wait <= 30 s                        -> wait that long, 1 retry
- 429 asking to wait longer                         -> cool down that long, next model
- 429 quota / billing (Gemini RESOURCE_EXHAUSTED)   -> switched off until the owner fixes it (no spend on retries)
- 500 / 502 / 503 / 504 / 529 (overloaded)          -> 1 retry; 3 errors in 5 minutes -> 5 minutes off, doubling to 60
- 401 / 403 (key)                                   -> switched off until the key changes
- 402 (balance)                                     -> switched off until the owner tops up
- 404 (model gone)                                  -> this model switched off; its replacement only with approval
- 400 (our request is wrong)                        -> stop: another brain would make the same mistake
- refusal                                           -> no retry
- an answer that is not the JSON we asked for       -> 1 re-ask
At most 4 calls per request and 120 seconds in all. After a cool-down the first call is the test («half open»): if it
works the model is back. A model is switched off per (company, model); the state survives a restart (SQLite).
Model changes are never made here: a replacement the provider names becomes a proposal for the owner (plan step 7)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time

import httpx

from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_state (provider TEXT NOT NULL, model TEXT NOT NULL, until REAL DEFAULT 0,
  off TEXT, key_fp TEXT, fails TEXT DEFAULT '[]', backoff REAL DEFAULT 300, note TEXT, ts REAL,
  PRIMARY KEY (provider, model));
CREATE TABLE IF NOT EXISTS llm_half (provider TEXT NOT NULL, model TEXT NOT NULL, since REAL NOT NULL,
  PRIMARY KEY (provider, model));
CREATE TABLE IF NOT EXISTS llm_events (ts REAL NOT NULL, slot TEXT, provider TEXT, model TEXT, outcome TEXT,
  kind TEXT, fallback INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS llm_events_ts ON llm_events(ts);
"""
MAX_CALLS, DEADLINE = 4, 120.0
OFF_RETRY = 6 * 3600         # billing / balance: one test call every 6 hours (the owner may have fixed it meanwhile)
HALF_TEST = 180              # a half-open test call in flight blocks other callers for at most this long
OVERLOAD = (500, 502, 503, 504, 529)
OFF_NOTES = {
    "key": "açar qəbul olunmadı — Admin-də açarı yeniləyin",
    "billing": "kvota və ya ödəniş — şirkətin saytında ödənişi (billing) qurun, ya da slotu söndürün",
    "balance": "balans bitib — şirkətin saytında balansı artırın",
    "model": "model artıq yoxdur — Admin-də təklif olunan modeli təsdiqləyin və ya rədd edin",
}


def _fp(key: str | None) -> str:
    return hashlib.sha256((key or "").encode()).hexdigest()[:16]


def classify(e: Exception) -> tuple[str, float | None]:
    """(kind, seconds to wait) for an error from llm.py, the SDKs or httpx."""
    from .llm import LLMError
    if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)):
        return "connect", None            # nothing was sent
    if isinstance(e, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError)):
        return "timeout", None
    if not isinstance(e, LLMError):
        return "other", None
    if e.hint in ("connect", "timeout", "refusal", "output", "config"):
        return e.hint, None
    st, body = e.status, (e.body or "").lower()
    if st in (401, 403) or (st == 400 and ("api key not valid" in body or "api_key_invalid" in body)):
        return "key", None
    if st == 402 or (st == 400 and "credit balance" in body):
        return "balance", None
    if st == 404:
        return "model", None
    if st in (408, 409):
        return "retry", None
    if st == 429:
        # Google's free tier puts «RESOURCE_EXHAUSTED», «quota» and «billing» into EVERY 429, the per-minute one too:
        # only a real no-billing / no-credit answer switches the model off; a per-day limit cools down to midnight PT
        if "insufficient_quota" in body or "limit: 0" in body or "credit balance" in body or \
                ("billing" in body and ("not enabled" in body or "enable billing" in body)):
            return "billing", None
        if "perday" in body or "per day" in body or "requests_per_day" in body:
            return "daily", e.retry_after
        return "rate", e.retry_after if e.retry_after is not None else 60.0
    if st in OVERLOAD:
        return "overload", e.retry_after
    if st == 400:
        return "bad_request", None
    return "other", None


class Router:
    def __init__(self, db: DB):
        self.db = db
        db.script(SCHEMA)

    # ---------- state ----------
    def _row(self, provider: str, model: str) -> dict:
        r = self.db.execute("SELECT * FROM llm_state WHERE provider=? AND model=?", (provider, model)).fetchone()
        return dict(r) if r else {"provider": provider, "model": model, "until": 0, "off": None, "key_fp": None,
                                  "fails": "[]", "backoff": 300, "note": None, "ts": None}

    def _save(self, r: dict) -> None:
        self.db.execute("INSERT INTO llm_state(provider, model, until, off, key_fp, fails, backoff, note, ts) "
                        "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(provider, model) DO UPDATE SET until=excluded.until, "
                        "off=excluded.off, key_fp=excluded.key_fp, fails=excluded.fails, backoff=excluded.backoff, "
                        "note=excluded.note, ts=excluded.ts",
                        (r["provider"], r["model"], r["until"], r["off"], r["key_fp"], r["fails"], r["backoff"],
                         r["note"], time.time()))

    def _half(self, provider: str, model: str) -> float | None:
        r = self.db.execute("SELECT since FROM llm_half WHERE provider=? AND model=?", (provider, model)).fetchone()
        return r["since"] if r else None

    def usable(self, provider: str, model: str, key: str | None, now: float | None = None) -> tuple[bool, str]:
        """May a call go now? After a cool-down (or every 6 h for billing / balance) exactly ONE test call goes
        («half open»); the others wait until it has answered."""
        now = time.time() if now is None else now
        r = self._row(provider, model)
        if r["off"] and r["off"] != "model" and r["key_fp"] and r["key_fp"] != _fp(key):
            r.update(off=None, note=None, until=0)       # a new key was saved: whatever the cause, try again
            self._save(r)
            return True, ""
        if r["off"] in ("key", "model"):
            return False, OFF_NOTES.get(r["off"], r["off"])
        if r["off"] and now < (r["ts"] or 0) + OFF_RETRY:
            return False, OFF_NOTES.get(r["off"], r["off"])
        if not r["off"] and r["until"] and now < r["until"]:
            return False, f"soyuyur: {round((r['until'] - now) / 60)} dəq ({r['note'] or ''})"
        if r["off"] or r["until"]:                       # time for the one test call
            h = self._half(provider, model)
            if h is not None and now - h < HALF_TEST:
                return False, "sınaq sorğusu gedir"
            return True, "test"                          # the caller marks it just before the call goes out
        return True, ""

    def mark_test(self, provider: str, model: str, now: float | None = None) -> None:
        self.db.execute("INSERT OR REPLACE INTO llm_half VALUES(?,?,?)",
                        (provider, model, time.time() if now is None else now))

    def ok(self, provider: str, model: str) -> None:
        self.db.execute("DELETE FROM llm_half WHERE provider=? AND model=?", (provider, model))
        r = self._row(provider, model)
        if r["until"] or r["fails"] != "[]" or r["off"]:
            r.update(until=0, fails="[]", backoff=300, note=None, off=None)   # the test worked: closed again
            self._save(r)

    def reset(self, provider: str, model: str) -> None:
        """The owner's «try again» in Admin."""
        self.db.execute("DELETE FROM llm_state WHERE provider=? AND model=?", (provider, model))
        self.db.execute("DELETE FROM llm_half WHERE provider=? AND model=?", (provider, model))

    def failed(self, provider: str, model: str, kind: str, wait: float | None, key: str | None,
               note: str = "", suggested: str | None = None, now: float | None = None) -> None:
        now = time.time() if now is None else now
        was_half = self._half(provider, model) is not None
        self.db.execute("DELETE FROM llm_half WHERE provider=? AND model=?", (provider, model))
        r = self._row(provider, model)
        if was_half and kind in ("overload", "timeout", "rate", "other", "connect") and r["until"]:
            r.update(until=now + r["backoff"], backoff=min(3600, r["backoff"] * 2), fails="[]",
                     note=(r["note"] or "") + " · sınaq alınmadı")       # the test failed: open again, longer
            self._save(r)
            return
        if kind in ("key", "billing", "balance", "model"):
            r.update(off=kind, key_fp=_fp(key), note=note[:200])
            if kind == "model" and suggested:
                self.propose(provider, model, suggested)
        elif kind == "daily":
            r.update(until=now + max(wait or 0, _to_pacific_midnight(now)), note="gündəlik kvota bitib")
        elif kind == "rate" and wait and wait > 30:
            r.update(until=now + wait, note="sorğu limiti")
        elif kind == "timeout":
            r.update(until=now + 120, note="cavab vaxtında gəlmədi")
        elif kind == "overload":
            fails = [t for t in json.loads(r["fails"] or "[]") if t > now - 300] + [now]
            r["fails"] = json.dumps(fails)
            if len(fails) >= 3:
                r.update(until=now + r["backoff"], backoff=min(3600, r["backoff"] * 2), fails="[]",
                         note="server yüklənib (3 xəta 5 dəqiqədə)")
        self._save(r)

    # ---------- proposals (plan step 7) ----------
    def propose(self, provider: str, old: str, new: str) -> None:
        props = json.loads(self.db.get("llm:proposals") or "{}")
        props[f"{provider}:{old}"] = {"provider": provider, "old": old, "new": new, "ts": time.time(),
                                      "status": "sahibin qərarını gözləyir"}
        self.db.put("llm:proposals", json.dumps(props, ensure_ascii=False))

    # ---------- the events (who answered, fallback rate) ----------
    def event(self, slot: str, provider: str, model: str, outcome: str, kind: str = "", fallback: bool = False):
        self.db.execute("INSERT INTO llm_events VALUES(?,?,?,?,?,?,?)",
                        (time.time(), slot, provider, model, outcome, kind, int(fallback)))


def _to_pacific_midnight(now: float) -> float:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    pt = datetime.fromtimestamp(now, ZoneInfo("America/Los_Angeles"))
    nxt = (pt + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return nxt.timestamp() - now


def budget() -> dict:
    """One request's limits, shared by every router call it makes (run_both asks up to three brains)."""
    return {"t0": time.time(), "calls": 0}


async def call(db: DB, slot: str, chain: list[tuple[str, str, str | None]], fn, ctx: dict | None = None,
               deadline: float = DEADLINE):
    """Try the chain [(provider, model, key)] with the rules above. fn(provider, model, key) -> result (awaitable).
    Returns (result, provider, model, fallback_used, errors). Never raises (except cancellation)."""
    rt = Router(db)
    ctx = ctx if ctx is not None else budget()
    t0 = ctx["t0"]
    errors = []
    for i, (provider, model, key) in enumerate(chain):
        if not provider or not model:
            continue
        if not key:
            errors.append(f"{provider}: açar yoxdur")
            continue
        can, why = rt.usable(provider, model, key)
        if not can:
            errors.append(f"{provider}: {why}")
            continue
        tries = 0
        while ctx["calls"] < MAX_CALLS:
            left = deadline - (time.time() - t0)
            if left < 10:
                errors.append(f"{provider}: vaxt qalmadı ({round(deadline)} san)")
                return None, None, None, False, errors
            ctx["calls"] += 1
            tries += 1
            if why == "test" and tries == 1:
                rt.mark_test(provider, model)          # only now: the one half-open test is really going out
            try:
                res = await asyncio.wait_for(fn(provider, model, key), timeout=left)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                kind, wait = classify(e)
                msg = (str(e) or type(e).__name__ or "vaxt bitdi").replace(key, "***")[:200]
                errors.append(f"{provider}: {msg}")
                try:
                    rt.failed(provider, model, kind, wait, key, msg, getattr(e, "suggested", None))
                    rt.event(slot, provider, model, "error", kind, i > 0)
                except Exception:       # the router's own record never decides the answer
                    pass
                if kind in ("bad_request", "config"):
                    break               # not retried on this model; the next model in the chain may accept it
                again = tries == 1 and (kind in ("connect", "retry", "overload", "output") or
                                        (kind == "rate" and wait is not None and wait <= 30))
                if not again or not rt.usable(provider, model, key)[0]:   # the breaker may have just opened
                    break
                await asyncio.sleep(min(wait, 30) if (kind == "rate" and wait) else random.uniform(0.5, 4.0))
                continue
            try:                         # the answer is kept even if writing the router's state fails
                rt.ok(provider, model)
                rt.event(slot, provider, model, "ok", "", i > 0)
            except Exception:
                pass
            return res, provider, model, i > 0, errors
    return None, None, None, False, errors


def view(db: DB) -> dict:
    """For the diagnostics and Admin: models off or cooling down (with what the owner can do), proposals, and per
    slot over the last 24 hours: calls, errors, how often the fallback answered."""
    Router(db)
    now = time.time()
    rows = [dict(r) for r in db.execute("SELECT provider, model, until, off, note FROM llm_state").fetchall()]
    state = [{"provider": r["provider"], "model": r["model"],
              "state": ("söndürülüb: " + OFF_NOTES.get(r["off"], r["off"])) if r["off"] else
                       (f"soyuyur ({round((r['until'] - now) / 60)} dəq): {r['note']}" if r["until"] > now else "işləyir")}
             for r in rows]
    db.execute("DELETE FROM llm_events WHERE ts < ?", (now - 30 * 86400,))
    ev = db.execute("SELECT slot, outcome, fallback, COUNT(*) n FROM llm_events WHERE ts > ? GROUP BY slot, outcome, "
                    "fallback", (now - 86400,)).fetchall()
    slots: dict[str, dict] = {}
    for r in ev:
        s = slots.setdefault(r["slot"] or "?", {"ok": 0, "error": 0, "fallback_ok": 0})
        s[r["outcome"]] = s.get(r["outcome"], 0) + r["n"]
        if r["outcome"] == "ok" and r["fallback"]:
            s["fallback_ok"] += r["n"]
    for s in slots.values():
        s["fallback_rate"] = round(s["fallback_ok"] / s["ok"], 3) if s["ok"] else None
        s["alert"] = bool(s["ok"] >= 10 and s["fallback_rate"] and s["fallback_rate"] > 0.2)
    month = {}                         # plan step 7: the brains' monthly report (cost, answers, errors per slot)
    try:
        for r in db.execute("SELECT slot, provider, model, SUM(ok) ok, COUNT(*) n, ROUND(SUM(usd), 4) usd FROM "
                            "brain_calls WHERE ts > ? GROUP BY slot, provider, model", (now - 30 * 86400,)).fetchall():
            month.setdefault(r["slot"], []).append({"brain": f"{r['provider']} · {r['model']}", "ok": r["ok"],
                                                    "calls": r["n"], "usd": r["usd"]})
    except Exception:
        pass
    return {"models": [x for x in state if x["state"] != "işləyir"], "proposals":
            json.loads(db.get("llm:proposals") or "{}"), "slots_24h": slots, "month": month}


def decide(db: DB, keys, action: str, provider: str, model: str) -> dict:
    """The owner's buttons in Admin. «reset»: try this model again now. «approve»: the proposed replacement takes the
    retired model's place in every slot that used it (the owner's own model decision). «reject»: keep it off."""
    from . import brains, registry
    rt = Router(db)
    if action == "reset":
        rt.reset(provider, model)
        return {"ok": True, "note": f"{provider} · {model}: yenidən sınanacaq"}
    props = json.loads(db.get("llm:proposals") or "{}")
    p = props.get(f"{provider}:{model}")
    if not p:
        raise ValueError("belə təklif yoxdur")
    if action == "approve":
        moved = []
        for b in registry.BRAIN_SLOTS:
            cfg = brains.config(db, b["id"])
            ch = {}
            if cfg.get("provider") == provider and cfg.get("model") == model:
                ch["model"] = p["new"]
            if cfg.get("fallback") == provider and cfg.get("fallback_model") == model:
                ch["fallback_model"] = p["new"]
            if ch:
                brains.save(db, b["id"], ch)
                moved.append(b["id"])
        p["status"] = f"təsdiqləndi ({', '.join(moved) or 'heç bir yuva istifadə etmirdi'})"
    elif action == "reject":
        p["status"] = "rədd edildi: köhnə model söndürülü qalır"
    else:
        raise ValueError("naməlum əməliyyat")
    p["decided"] = time.time()
    db.put("llm:proposals", json.dumps(props, ensure_ascii=False))
    return {"ok": True, "note": p["status"]}
