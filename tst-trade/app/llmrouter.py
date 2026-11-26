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
CREATE TABLE IF NOT EXISTS llm_events (ts REAL NOT NULL, slot TEXT, provider TEXT, model TEXT, outcome TEXT,
  kind TEXT, fallback INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS llm_events_ts ON llm_events(ts);
"""
MAX_CALLS, DEADLINE = 4, 120.0
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
    if isinstance(e, httpx.ConnectError) or isinstance(e, httpx.ConnectTimeout):
        return "connect", None
    if isinstance(e, httpx.TimeoutException):
        return "timeout", None
    if not isinstance(e, LLMError):
        return "other", None
    if e.hint in ("connect", "timeout", "refusal", "output", "config"):
        return e.hint, None
    st, body = e.status, (e.body or "").lower()
    if st in (401, 403):
        return "key", None
    if st == 402:
        return "balance", None
    if st == 404:
        return "model", None
    if st in (408, 409):
        return "retry", None
    if st == 429:
        if any(w in body for w in ("billing", "resource_exhausted", "quota", "insufficient_quota", "credit")):
            if "per day" in body or "perday" in body or "requests_per_day" in body:
                return "daily", e.retry_after
            return "billing", None
        return "rate", e.retry_after
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
                                  "fails": "[]", "backoff": 300, "note": None}

    def _save(self, r: dict) -> None:
        self.db.execute("INSERT INTO llm_state(provider, model, until, off, key_fp, fails, backoff, note, ts) "
                        "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(provider, model) DO UPDATE SET until=excluded.until, "
                        "off=excluded.off, key_fp=excluded.key_fp, fails=excluded.fails, backoff=excluded.backoff, "
                        "note=excluded.note, ts=excluded.ts",
                        (r["provider"], r["model"], r["until"], r["off"], r["key_fp"], r["fails"], r["backoff"],
                         r["note"], time.time()))

    def usable(self, provider: str, model: str, key: str | None, now: float | None = None) -> tuple[bool, str]:
        now = time.time() if now is None else now
        r = self._row(provider, model)
        if r["off"]:
            if r["off"] == "key" and r["key_fp"] and r["key_fp"] != _fp(key):
                r["off"] = r["note"] = None              # a new key was saved: try again
                self._save(r)
                return True, ""
            return False, OFF_NOTES.get(r["off"], r["off"])
        if r["until"] and now < r["until"]:
            return False, f"soyuyur: {round((r['until'] - now) / 60)} dəq ({r['note'] or ''})"
        return True, ""

    def ok(self, provider: str, model: str) -> None:
        r = self._row(provider, model)
        if r["until"] or r["fails"] != "[]" or r["off"]:
            r.update(until=0, fails="[]", backoff=300, note=None)   # the half-open test worked: closed again
            if r["off"] in ("billing", "balance"):
                r["off"] = None
            self._save(r)

    def failed(self, provider: str, model: str, kind: str, wait: float | None, key: str | None,
               note: str = "", suggested: str | None = None, now: float | None = None) -> None:
        now = time.time() if now is None else now
        r = self._row(provider, model)
        if kind in ("key", "billing", "balance", "model"):
            r.update(off=kind, key_fp=_fp(key), note=note[:200])
            if kind == "model" and suggested:
                self.propose(provider, model, suggested)
        elif kind == "daily":
            r.update(until=now + (wait or _to_pacific_midnight(now)), note="gündəlik kvota bitib")
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


async def call(db: DB, slot: str, chain: list[tuple[str, str, str | None]], fn, deadline: float = DEADLINE):
    """Try the chain [(provider, model, key)] with the rules above. fn(provider, model, key) -> result (awaitable).
    Returns (result, provider, model, fallback_used, errors). Never raises."""
    rt = Router(db)
    t0 = time.time()
    calls, errors = 0, []
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
        while calls < MAX_CALLS and time.time() - t0 < deadline:
            calls += 1
            tries += 1
            try:
                res = await asyncio.wait_for(fn(provider, model, key), timeout=max(5.0, deadline - (time.time() - t0)))
                rt.ok(provider, model)
                rt.event(slot, provider, model, "ok", "", i > 0)
                return res, provider, model, i > 0, errors
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if isinstance(e, asyncio.TimeoutError):
                    kind, wait = "timeout", None
                else:
                    kind, wait = classify(e)
                msg = str(e).replace(key, "***")[:200]
                errors.append(f"{provider}: {msg}")
                rt.failed(provider, model, kind, wait, key, msg, getattr(e, "suggested", None))
                rt.event(slot, provider, model, "error", kind, i > 0)
                if kind == "bad_request" or kind == "config":
                    return None, provider, model, i > 0, errors      # our own mistake: another brain would repeat it
                again = tries == 1 and (kind in ("connect", "retry", "overload", "output") or
                                        (kind == "rate" and wait is not None and wait <= 30))
                if not again or not rt.usable(provider, model, key)[0]:   # the breaker may have just opened
                    break
                await asyncio.sleep(min(wait, 30) if (kind == "rate" and wait) else random.uniform(0.5, 4.0))
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
    return {"models": [x for x in state if x["state"] != "işləyir"], "proposals":
            json.loads(db.get("llm:proposals") or "{}"), "slots_24h": slots}
