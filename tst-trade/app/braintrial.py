"""Beyinlərin sınaq sürüşü və qabaqcadan icazə (owner 2026-11-26, plan step 7).

When a provider retires a model and names a replacement, the replacement is first tried on a fixed set of 20 tasks
whose answers are known in advance (no web, no prices): pull the exact figure and its period out of a short market
text, and label the direction of a headline whose direction is unambiguous. Score = share answered exactly right in
valid JSON; cost and time are measured too. The owner's pre-approval rule (one decision, 2026-11-26):
  same company  AND  score not lower than the old model's last score (or >= 0.9 when the old one is gone)
  AND  price per token at most +20 %  ->  the new model takes the old one's place by itself and the owner is told;
otherwise the proposal waits for the owner in Admin with the trial's numbers on its card.
Costs a few cents per trial; at most one trial per proposal."""
from __future__ import annotations

import asyncio
import json
import time

from .db import DB

TASKS = [
    # (text, expected value, expected period) — extraction
    ("India's gold imports rose to $14.7 billion in October 2026, the commerce ministry said.", 14.7, "2026-10"),
    ("The People's Bank of China added 5 tonnes of gold in September 2026, its eleventh monthly purchase.", 5.0, "2026-09"),
    ("Global gold ETFs saw net inflows of 38.6 tonnes in August 2026, the World Gold Council reported.", 38.6, "2026-08"),
    ("COMEX gold inventories stood at 41.2 million ounces on 2026-11-20, CME data showed.", 41.2, "2026-11-20"),
    ("The IBJA rate for 24-carat gold was 128450 rupees per 10 grams on 2026-11-26.", 128450.0, "2026-11-26"),
    ("Gold discounts in India widened to $12 an ounce in the week ending 2026-11-21.", 12.0, "2026-11-21"),
    ("Chinese premiums over London prices were $8 an ounce in the week ending 2026-11-14.", 8.0, "2026-11-14"),
    ("The RBI held 880.2 tonnes of gold at the end of June 2026, its bulletin said.", 880.2, "2026-06"),
    ("US nonfarm payrolls rose by 151000 in October 2026, the Labor Department said.", 151000.0, "2026-10"),
    ("Swiss gold exports to India reached 22.5 tonnes in July 2026, customs data showed.", 22.5, "2026-07"),
]
LABELS = [
    ("Gold jumps to a record as the Fed signals deep rate cuts", "up"),
    ("Gold slumps as the dollar surges after hot US jobs data", "down"),
    ("Central banks' gold buying hits a record pace, WGC says", "up"),
    ("Gold tumbles as Treasury yields spike to a 16-year high", "down"),
    ("Safe-haven gold soars as war fears grip markets", "up"),
    ("Gold sinks as risk appetite returns and stocks rally to records", "down"),
    ("Gold rallies after US inflation comes in far above forecasts and the dollar falls", "up"),
    ("Gold drops sharply as the Fed signals more rate hikes", "down"),
    ("Indian gold demand surges ahead of Diwali, imports jump", "up"),
    ("Gold falls as ETF holders sell for a fifth straight week", "down"),
]
SYSTEM = ("You are tested on exact reading. For each item answer ONLY from the given text. Reply with one JSON object: "
          '{"answers": [{"i": number, "value": number|null, "period": "YYYY-MM or YYYY-MM-DD"|null, '
          '"direction": "up"|"down"|null}]}')
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answers"], "properties": {"answers": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["i", "value", "period", "direction"],
                               "properties": {"i": {"type": "integer"}, "value": {"type": ["number", "null"]},
                                              "period": {"type": ["string", "null"]},
                                              "direction": {"type": ["string", "null"]}}}}}}


def prompt() -> str:
    lines = [f"{i}. EXTRACT the figure and its period: {t}" for i, (t, _, _) in enumerate(TASKS)]
    lines += [f"{len(TASKS) + i}. LABEL gold's direction (up/down): {t}" for i, (t, _) in enumerate(LABELS)]
    return "\n".join(lines)


def score(data: dict | None) -> float:
    if not isinstance(data, dict):
        return 0.0
    got = {a.get("i"): a for a in data.get("answers", []) if isinstance(a, dict)}
    ok = 0
    for i, (_, v, per) in enumerate(TASKS):
        a = got.get(i) or {}
        try:
            ok += int(abs(float(a.get("value")) - v) <= 1e-6 * max(1, abs(v)) and str(a.get("period")) == per)
        except (TypeError, ValueError):
            pass
    for i, (_, d) in enumerate(LABELS):
        ok += int((got.get(len(TASKS) + i) or {}).get("direction") == d)
    return ok / (len(TASKS) + len(LABELS))


async def trial(db: DB, provider: str, model: str, key: str) -> dict:
    from . import llm
    t0 = time.time()
    try:
        data, tin, tout = await asyncio.wait_for(llm.ask(provider, key, model, SYSTEM, prompt(), SCHEMA, 1500), 90)
        res = {"score": round(score(data), 3), "usd": round(llm.cost(model, tin, tout), 5), "ok": True}
    except Exception as e:
        res = {"score": 0.0, "usd": 0.0, "ok": False,                     # mask the key BEFORE cutting the text
               "error": (str(e) or type(e).__name__).replace(key, "***")[:160],
               "note": "sınaq alınmadı: müvəqqəti xətadırsa 6 saatdan sonra yenə (ən çox 3 dəfə), yoxsa qərar sahibindədir"}
    res.update({"provider": provider, "model": model, "seconds": round(time.time() - t0, 1), "ts": time.time()})
    scores = json.loads(db.get("braintrial:scores") or "{}")
    scores[f"{provider}:{model}"] = res
    db.put("braintrial:scores", json.dumps(scores))
    return res


def preapproved(db: DB, provider: str, old: str, new: str, new_res: dict) -> tuple[bool, str]:
    """The owner's rule: same company, not worse on the trial, at most +20 % per token."""
    from . import llm
    scores = json.loads(db.get("braintrial:scores") or "{}")
    old_res = scores.get(f"{provider}:{old}")
    bar = old_res["score"] if old_res and old_res.get("ok") else 0.9
    if not new_res.get("ok") or new_res["score"] < bar:
        return False, f"sınaqda {new_res.get('score')} (lazım: ≥ {bar})"
    po, pn = llm.PRICES.get(old), llm.PRICES.get(new)
    if not pn:
        return False, "yeni modelin qiyməti cədvəldə yoxdur"
    if not po:
        return False, "köhnə modelin qiyməti məlum deyil: müqayisə edilə bilmir"
    if pn[0] > po[0] * 1.2 or pn[1] > po[1] * 1.2:
        return False, f"qiymət 20 %-dən çox artır ({po} → {pn} $/mln token)"
    return True, f"sınaq {new_res['score']} ≥ {bar}, qiymət ≤ +20 %"


TRANSIENT = ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504", "high demand", "Timeout", "timed out",
             "overloaded")
RETRY_AFTER, RETRY_MAX = 6 * 3600, 3


def _retry_due(p: dict, now: float) -> bool:
    """A trial the provider could not run for a passing reason (busy, a timeout) is tried again later — 27.11: the new
    Gemini model's only trial hit Google's «high demand» 503 and the proposal then waited for the owner for ever."""
    t = p.get("trial") or {}
    if t.get("ok") or int(p.get("trial_attempts") or 1) >= RETRY_MAX:
        return False
    return any(x in str(t.get("error") or "") for x in TRANSIENT) and now - float(t.get("ts") or 0) > RETRY_AFTER


async def handle_proposals(db: DB, keys) -> list[str]:
    """For each waiting proposal: one trial; if the owner's rule holds, apply it (and say so); else leave the card."""
    from . import llmrouter
    props = json.loads(db.get("llm:proposals") or "{}")
    done = []
    now = time.time()
    for k, p in props.items():
        if not str(p.get("status", "")).startswith("sahibin") or (p.get("trial") and not _retry_due(p, now)):
            continue
        attempts = int(p.get("trial_attempts") or (1 if p.get("trial") else 0)) + 1
        key = keys.first(p["provider"]) if keys is not None else None
        if not key:
            continue
        res = await trial(db, p["provider"], p["new"], key)
        ok, why = preapproved(db, p["provider"], p["old"], p["new"], res)
        # the owner may have decided while the trial ran (up to 90 s): re-read and touch only this proposal
        fresh = json.loads(db.get("llm:proposals") or "{}")
        cur = fresh.get(k)
        if not cur or not str(cur.get("status", "")).startswith("sahibin") or \
                (cur.get("trial") and not _retry_due(cur, now)):
            continue
        cur["trial"], cur["rule"], cur["trial_attempts"] = res, why, attempts
        db.put("llm:proposals", json.dumps(fresh, ensure_ascii=False))
        if ok:
            out = llmrouter.decide(db, keys, "approve", p["provider"], p["old"])
            props = json.loads(db.get("llm:proposals") or "{}")
            props[k]["status"] = "qabaqcadan icazə ilə keçdi: " + why + " · " + out["note"]
            db.put("llm:proposals", json.dumps(props, ensure_ascii=False))
            done.append(f"{p['provider']} {p['old']} → {p['new']}")
    return done
