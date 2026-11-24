"""Brain slots. A slot is defined by its job (registry.BRAIN_SLOTS); the brain in it is a setting the owner changes
on the admin page. In this first version no slot takes part in forecasts yet: the forecast desks are code, and each
slot is connected and measured by the Judge in its own next step."""
from __future__ import annotations

import json

from . import registry
from .db import DB
from .keys import KeyStore

EDITABLE = ("provider", "model", "fallback", "fallback_model", "month_usd")
IN_USE = ("scout", "hunter", "reader", "strategist", "analyst2", "reviewer", "chartist")   # slots that already do their job; the others are configured and checked only


def config(db: DB, slot: str) -> dict:
    base = next(b for b in registry.BRAIN_SLOTS if b["id"] == slot)
    saved = json.loads(db.get(f"brain:{slot}") or "{}")
    cfg = {k: base.get(k) for k in ("provider", "model", "fallback", "fallback_model")}
    cfg["month_usd"] = 20.0
    cfg.update({k: v for k, v in saved.items() if k in EDITABLE})
    return cfg


def save(db: DB, slot: str, values: dict) -> dict:
    if slot not in registry.BRAIN_IDS:
        raise ValueError("naməlum yuva")
    cfg = config(db, slot)
    for k in EDITABLE:
        if k not in values:
            continue
        v = values[k]
        if k in ("provider", "fallback"):
            if v in ("", None):
                v = None
            elif v not in registry.BRAIN_PROVIDERS:
                raise ValueError(f"naməlum provayder: {v}")
        elif k == "month_usd":
            v = float(v)
            if not 0 <= v <= 1000:
                raise ValueError("aylıq limit 0–1000 $ olmalıdır")
        else:
            v = (str(v).strip() or None) if v is not None else None
        cfg[k] = v
    if not cfg["provider"] or not cfg["model"]:
        raise ValueError("provayder və model boş ola bilməz")
    db.put(f"brain:{slot}", json.dumps(cfg))
    return cfg


def view(db: DB, keys: KeyStore) -> list[dict]:
    out = []
    for b in registry.BRAIN_SLOTS:
        cfg = config(db, b["id"])
        ks = keys.status(cfg["provider"])
        if not ks["saved"]:
            state = "açar yoxdur"
        elif ks["unreadable"]:
            state = "açarı yenidən daxil edin"
        elif ks["check"] and ks["check"]["ok"] is False:
            state = "xəta"
        elif ks["check"] and ks["check"]["ok"]:
            state = "hazırdır"
        else:
            state = "yoxlanmayıb"
        out.append({**{k: b[k] for k in ("id", "name", "job", "may_not", "why")},
                    "requirements": [{"name": n, "weight": w} for n, w in b["requirements"]],
                    "config": cfg, "state": state, "in_use": b["id"] in IN_USE,
                    "spent": round(spent(db, b["id"]), 4), "last_call": last_call(db, b["id"]),
                    "default": {k: b[k] for k in ("provider", "model", "fallback", "fallback_model")}})
    return out


# ---------- running a slot ----------
import time as _time  # noqa: E402

from . import llm  # noqa: E402

CALLS_SCHEMA = """
CREATE TABLE IF NOT EXISTS brain_calls (ts REAL NOT NULL, slot TEXT NOT NULL, provider TEXT, model TEXT, ok INTEGER,
  tin INTEGER, tout INTEGER, usd REAL, error TEXT);
CREATE INDEX IF NOT EXISTS brain_calls_ts ON brain_calls(slot, ts);
"""


def _month_start(now: float) -> float:
    import calendar
    t = _time.gmtime(now)
    return float(calendar.timegm((t.tm_year, t.tm_mon, 1, 0, 0, 0)))


def pace(db: DB, slot: str, now: float | None = None) -> float:
    """Cost thermostat (Block 12): if this month's spend, projected to the month's end, would pass 90 % of the slot's
    limit, the slot's regular jobs run half as often (factor 2); otherwise 1. Alarms are capped separately."""
    import calendar
    from datetime import datetime, timezone
    now = _time.time() if now is None else now
    d = datetime.fromtimestamp(now, timezone.utc)
    days = calendar.monthrange(d.year, d.month)[1]
    elapsed = max(0.5, (now - _month_start(now)) / 86400)
    projected = spent(db, slot, now) / elapsed * days
    return 2.0 if projected > 0.9 * float(config(db, slot)["month_usd"]) else 1.0


def spent(db: DB, slot: str, now: float | None = None) -> float:
    now = _time.time() if now is None else now
    db.script(CALLS_SCHEMA)
    r = db.execute("SELECT COALESCE(SUM(usd), 0) s FROM brain_calls WHERE slot=? AND ts>=?",
                   (slot, _month_start(now))).fetchone()
    return float(r["s"])


def last_call(db: DB, slot: str) -> dict | None:
    db.script(CALLS_SCHEMA)
    r = db.execute("SELECT ts, provider, model, ok, error FROM brain_calls WHERE slot=? ORDER BY ts DESC LIMIT 1",
                   (slot,)).fetchone()
    return dict(r) if r else None


async def run(db: DB, keys: KeyStore, slot: str, system: str, user: str, schema: dict,
              max_tokens: int = 2000, search: bool = False) -> tuple[dict | None, str]:
    """Ask the slot's brain, then its fallback. Returns (answer or None, a line for the panel). Never raises."""
    db.script(CALLS_SCHEMA)
    cfg = config(db, slot)
    if spent(db, slot) >= float(cfg["month_usd"]):
        return None, f"aylıq limit doldu ({cfg['month_usd']} $)"
    errors = []
    for provider, model in ((cfg["provider"], cfg["model"]), (cfg.get("fallback"), cfg.get("fallback_model"))):
        if not provider or not model:
            continue
        key = keys.first(provider)
        if not key:
            errors.append(f"{provider}: açar yoxdur")
            continue
        try:
            calls = 0
            if search:
                data, tin, tout, calls = await llm.search(provider, key, model, system, user, max_tokens)
            else:
                data, tin, tout = await llm.ask(provider, key, model, system, user, schema, max_tokens)
            db.execute("INSERT INTO brain_calls VALUES(?,?,?,?,1,?,?,?,NULL)",
                       (_time.time(), slot, provider, model, tin, tout,
                        llm.cost(model, tin, tout) + calls * llm.SEARCH_CALL_USD))
            if not search:      # Block 17: count numbers the brain wrote that it was not given
                from . import checker
                checker.record(db, slot, data, user + "\n" + system)
            return data, f"{provider} · {model}"
        except Exception as e:   # a broken brain must never stop the system
            msg = str(e).replace(key, "***")[:200]
            errors.append(f"{provider}: {msg}")
            db.execute("INSERT INTO brain_calls VALUES(?,?,?,?,0,0,0,0,?)", (_time.time(), slot, provider, model, msg))
    return None, "; ".join(errors) or "beyin seçilməyib"


async def run_both(db: DB, keys: KeyStore, slot: str, system: str, user: str,
                   max_tokens: int = 2000) -> list[tuple[dict | None, str]]:
    """Ask the slot's main brain AND its second brain independently, both with live web search: for jobs where two
    independent answers must agree before anything is used (a figure found on the web). Never raises."""
    db.script(CALLS_SCHEMA)
    cfg = config(db, slot)
    if spent(db, slot) >= float(cfg["month_usd"]):
        return [(None, f"aylıq limit doldu ({cfg['month_usd']} $)")]
    out = []
    for provider, model in ((cfg["provider"], cfg["model"]), (cfg.get("fallback"), cfg.get("fallback_model"))):
        if not provider or not model:
            out.append((None, "ikinci beyin seçilməyib"))
            continue
        key = keys.first(provider)
        if not key:
            out.append((None, f"{provider}: açar yoxdur"))
            continue
        try:
            data, tin, tout, calls = await llm.search(provider, key, model, system, user, max_tokens)
            db.execute("INSERT INTO brain_calls VALUES(?,?,?,?,1,?,?,?,NULL)",
                       (_time.time(), slot, provider, model, tin, tout,
                        llm.cost(model, tin, tout) + calls * llm.SEARCH_CALL_USD))
            out.append((data, f"{provider} · {model}"))
        except Exception as e:   # a broken brain must never stop the system
            msg = str(e).replace(key, "***")[:200]
            db.execute("INSERT INTO brain_calls VALUES(?,?,?,?,0,0,0,0,?)", (_time.time(), slot, provider, model, msg))
            out.append((None, f"{provider}: {msg}"))
    return out
