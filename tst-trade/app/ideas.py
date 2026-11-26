"""Fərziyyə agenti (Radar Gold scheme R2 + R3, owner 2026-11-25: «1-2 ed»).

R2 — a brain reads the research memory (every rule's record after costs: per metal, per ADX regime, the stop+target
result, and how the earlier ideas turned out) and proposes at most two NEW measurable ideas a week. It never sees
prices and never writes a price; it may only fill the allowed template below.

R3 — this code turns an idea into a rule (HY-n) without any freedom: a filter of an existing rule's firings —
  metals, direction, market regime (ADX), New York hours of the candle's close, confirmation by another rule in the
  same direction within k candles, an agreeing fundamental rule known in the last 5 days.
Its firings are copies of the base rule's firings that pass the filter, so the Judge measures it exactly like every
other rule (after costs, both halves, stop+target, robustness), the attempts counter grows with it, and it can only
become usable through the one-look final test on LATER data, the independent re-check and the owner's approval —
the same road as every rule. An idea found by looking at history is only a candidate until then: the final test is
what makes the in-sample search honest. Nothing is switched on by itself."""
from __future__ import annotations

import json
import time
from bisect import bisect_left, bisect_right
from datetime import datetime
from zoneinfo import ZoneInfo

from .db import DB

NY = ZoneInfo("America/New_York")
SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, rule TEXT, base TEXT, tf TEXT,
  spec TEXT NOT NULL, why TEXT, expect TEXT, brain TEXT, status TEXT NOT NULL, reason TEXT);
"""
PER_WEEK = 2
MAX_ACTIVE = 30
MIN_BASE_N = 100
WEEK = 7 * 86400
TF_SEC = {"1h": 3600, "4h": 14400, "1d": 86400}

SYSTEM = (
    "You are the research hypothesis agent of a precious-metals forecasting system. You get the measured record of "
    "every trading rule (after the full trading cost) and how earlier ideas turned out. Propose at most two NEW, "
    "measurable ideas that could make an existing rule better by FILTERING when it is used. You may only use the "
    "template fields; you never write prices or forecasts. Prefer ideas with an economic reason (e.g. a breakout "
    "rule only in a trending regime, a reversal rule only in a range, a rule only when the fundamental side agrees, "
    "a rule only in the hours a market is liquid). Do not repeat an idea from the memory. Explain the reason in one "
    "or two sentences in Azerbaijani (Latin script), and say what result would prove it wrong.")

IDEA = {"type": "object", "additionalProperties": False,
        "required": ["base", "tf", "metals", "dir", "adx", "hour_from", "hour_to", "confirm_rule", "confirm_within",
                     "fa_context", "why", "expect"],
        "properties": {
            "base": {"type": "string"}, "tf": {"type": "string", "enum": ["1h", "4h", "1d"]},
            "metals": {"type": "array", "items": {"type": "string", "enum": ["XAU", "XAG", "XPT", "XPD"]}},
            "dir": {"type": "integer", "enum": [-1, 0, 1]},
            "adx": {"type": "array", "items": {"type": "integer", "enum": [0, 1, 2]}},
            "hour_from": {"type": "integer"}, "hour_to": {"type": "integer"},
            "confirm_rule": {"type": "string"}, "confirm_within": {"type": "integer"},
            "fa_context": {"type": "boolean"}, "why": {"type": "string"}, "expect": {"type": "string"}}}
OUT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["ideas"],
              "properties": {"ideas": {"type": "array", "items": IDEA}}}
TEMPLATE = (
    "Template (every field required): base = an existing rule id from the table; tf = its timeframe; metals = [] for "
    "all or a subset; dir = 1 only long firings, -1 only short, 0 both; adx = [] any regime or a subset of 0 (no trend, "
    "ADX<20), 1 (20-25), 2 (strong trend, ADX>25); hour_from/hour_to = New York hour range of the candle close "
    "(0-23, hour_from inclusive, hour_to exclusive, may wrap past midnight; -1/-1 = any hour; not for 1d); "
    "confirm_rule = another rule id that must have fired in the SAME direction on the same metal and timeframe within "
    "confirm_within candles (1-5) before or at the firing, or \"\" for none; fa_context = true: a fundamental (FA-) "
    "rule in the same direction must have been known in the last 5 days. At least one filter must be set.")


def ensure(db: DB) -> None:
    db.script(SCHEMA)


def _rules_known(db: DB) -> set[str]:
    return {r["rule"] for r in db.execute("SELECT DISTINCT rule FROM rule_signals WHERE mode != 'futures'").fetchall()}


def validate(db: DB, raw: dict, records: dict) -> tuple[dict | None, str]:
    """R3: the idea as a fixed spec, or the reason it cannot be used."""
    try:
        base, tf = str(raw["base"]).strip(), str(raw["tf"])
        if base.startswith("HY-") or base.startswith("FA-") or base.startswith("NW-"):
            return None, "baza texniki qayda olmalıdır"
        rec = (records.get(base) or {}).get(tf)
        if not rec:
            return None, f"{base} {tf} qaydası tapılmadı"
        if rec["n"] < MIN_BASE_N:
            return None, f"{base} {tf}: cəmi {rec['n']} hal (ən azı {MIN_BASE_N})"
        metals = sorted({m for m in raw.get("metals") or [] if m in ("XAU", "XAG", "XPT", "XPD")})
        d = int(raw.get("dir") or 0)
        adx = sorted({int(g) for g in raw.get("adx") or [] if int(g) in (0, 1, 2)})
        hf, ht = int(raw.get("hour_from", -1)), int(raw.get("hour_to", -1))
        hours = None
        if hf >= 0 or ht >= 0:
            if tf == "1d" or not (0 <= hf <= 23 and 0 <= ht <= 23) or hf == ht:
                return None, "saat aralığı düzgün deyil"
            hours = [hf, ht]
        conf = str(raw.get("confirm_rule") or "").strip()
        within = int(raw.get("confirm_within") or 0)
        if conf:
            if conf == base or conf.startswith("HY-") or not (records.get(conf) or {}).get(tf):
                return None, f"təsdiq qaydası {conf} {tf} tapılmadı"
            if not 1 <= within <= 5:
                return None, "təsdiq pəncərəsi 1-5 şam olmalıdır"
        spec = {"base": base, "tf": tf, "metals": metals if len(metals) < 4 else [], "dir": d if d in (-1, 1) else 0,
                "adx": adx if len(adx) < 3 else [], "hours": hours, "confirm": [conf, within] if conf else None,
                "fa": bool(raw.get("fa_context"))}
    except (KeyError, TypeError, ValueError):
        return None, "şablon pozulub"
    if not (spec["metals"] or spec["dir"] or spec["adx"] or spec["hours"] or spec["confirm"] or spec["fa"]):
        return None, "heç bir süzgəc yoxdur (baza qaydanın eynisidir)"
    canon = json.dumps(spec, sort_keys=True)
    if db.execute("SELECT 1 FROM ideas WHERE spec=? AND status='sınaqda'", (canon,)).fetchone():
        return None, "bu fikir artıq sınaqdadır"
    return spec, ""


def add(db: DB, spec: dict, why: str, expect: str, brain: str, now: float | None = None) -> str:
    """Register a validated idea as rule HY-n and build its history at once; the attempts counter grows."""
    ensure(db)
    now = time.time() if now is None else now
    db.execute("INSERT INTO ideas(ts, base, tf, spec, why, expect, brain, status) VALUES(?,?,?,?,?,?,?,'sınaqda')",
               (now, spec["base"], spec["tf"], json.dumps(spec, sort_keys=True), why[:400], expect[:300], brain[:80]))
    i = db.execute("SELECT MAX(id) i FROM ideas").fetchone()["i"]
    rule = f"HY-{i}"
    db.execute("UPDATE ideas SET rule=? WHERE id=?", (rule, i))
    from . import rigor
    seen = rigor._seen(db)
    seen.add(f"r:{rule}:{spec['tf']}")
    db.put("trials:seen", json.dumps(sorted(seen)))
    derive(db, rule, spec)
    return rule


def _hour_ok(t: int, tf: str, hours: list | None) -> bool:
    if not hours:
        return True
    h = datetime.fromtimestamp(t + TF_SEC[tf], NY).hour          # the hour the candle closed
    a, b = hours
    return a <= h < b if a < b else (h >= a or h < b)


def derive(db: DB, rule: str, spec: dict) -> int:
    """The HY rule's firings: the base rule's firings that pass every filter (outcomes are copied; firings whose
    outcome is still open get it from the rules job like any other rule)."""
    tf, step = spec["tf"], TF_SEC[spec["tf"]]
    conf = {}
    if spec.get("confirm"):
        for r in db.execute("SELECT metal, t, dir FROM rule_signals WHERE rule=? AND tf=? AND mode!='futures' ORDER BY t",
                            (spec["confirm"][0], tf)).fetchall():
            conf.setdefault((r["metal"], r["dir"]), []).append(r["t"])
    fa = {}
    if spec.get("fa"):
        for r in db.execute("SELECT metal, t, dir FROM rule_signals WHERE rule LIKE 'FA-%' ORDER BY t").fetchall():
            fa.setdefault((r["metal"], r["dir"]), []).append(r["t"] + 86400)        # known after its day closed
    from .rules import regime
    rows = []
    for r in db.execute("SELECT metal, t, dir, price0, price1, mode, atr, rr, held, adx FROM rule_signals "
                        "WHERE rule=? AND tf=? AND mode!='futures'", (spec["base"], tf)).fetchall():
        if spec["metals"] and r["metal"] not in spec["metals"]:
            continue
        if spec["dir"] and r["dir"] != spec["dir"]:
            continue
        if spec["adx"] and regime(r["adx"]) not in spec["adx"]:
            continue
        if not _hour_ok(r["t"], tf, spec.get("hours")):
            continue
        if spec.get("confirm"):
            ts = conf.get((r["metal"], r["dir"]), [])
            if bisect_right(ts, r["t"]) == bisect_left(ts, r["t"] - spec["confirm"][1] * step):
                continue
        if spec.get("fa"):
            ts = fa.get((r["metal"], r["dir"]), [])
            known_at = r["t"] + step
            if bisect_right(ts, known_at) == bisect_left(ts, known_at - 5 * 86400):
                continue
        rows.append((r["metal"], tf, r["t"], rule, r["dir"], r["price0"], r["price1"], r["mode"],
                     f"{spec['base']} + süzgəc", r["atr"], r["rr"], r["held"], r["adx"]))
    db.executemany("INSERT OR IGNORE INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note, atr, rr, "
                   "held, adx) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def derive_all(db: DB) -> int:
    """Called by the rules job after the base rules: new base firings reach the HY rules."""
    ensure(db)
    n = 0
    for r in db.execute("SELECT rule, spec FROM ideas WHERE status='sınaqda' AND rule IS NOT NULL").fetchall():
        n += derive(db, r["rule"], json.loads(r["spec"]))
    return n


def memory(db: DB, records: dict) -> str:
    """What the brain is given: the rule table (biggest cells first) and the earlier ideas with their results."""
    cells = []
    for rule, tfs in records.items():
        if rule.startswith(("FA-", "NW-")):
            continue
        for tf, x in tfs.items():
            if x["n"] >= MIN_BASE_N or rule.startswith("HY-"):
                rr = x.get("rr") or {}
                cells.append((x["n"], f"{rule} {tf}: n={x['n']} hit={x['hit_rate']} net={x['net_avg']} "
                                      f"R_net={rr.get('net_r')} status={x['status']} "
                                      f"adx={ {k: (v['n'], v['hit_rate']) for k, v in (x.get('by_adx') or {}).items()} } "
                                      f"metals={ {m: (v['n'], v['hit_rate']) for m, v in (x.get('by_metal') or {}).items()} }"))
    cells.sort(reverse=True)
    try:                                # plan step 11: a miss cause far more frequent than before is a lead to test
        from . import autopsy
        for h in (autopsy.view(db) or {}).get("hints") or []:
            cells.insert(0, (10 ** 9, f"SƏHV YARILMASI: «{h['cause']}» səbəbli qaçırışlar {h['share']} (əvvəl "
                                      f"{h['before']}), z={h['z']} — bunu aradan qaldıran filtr fikri sınana bilər"))
    except Exception:
        pass
    mem = [f"{r['rule'] or '-'} ({r['status']}): {r['spec']} — {r['why'] or ''} {('[' + r['reason'] + ']') if r['reason'] else ''}"
           for r in db.execute("SELECT * FROM ideas ORDER BY id DESC LIMIT 30").fetchall()]
    return ("Rule records (net = average result after the full cost per firing; R_net = stop+target result in risk "
            "units after cost):\n" + "\n".join(c for _, c in cells[:70]) +
            "\n\nEarlier ideas (do not repeat):\n" + ("\n".join(mem) or "none yet") + "\n\n" + TEMPLATE)


def due(db: DB, now: float) -> bool:
    """Sunday from 14:00 UTC (the metal markets are closed: research does not compete with live work), once a week."""
    ensure(db)
    d = datetime.fromtimestamp(now, ZoneInfo("UTC"))
    if d.weekday() != 6 or d.hour < 14:
        return False
    last = float(db.get("ideas:last") or 0)
    active = db.execute("SELECT COUNT(*) n FROM ideas WHERE status='sınaqda'").fetchone()["n"]
    return now - last >= WEEK and active < MAX_ACTIVE


def _weekly_skip(db: DB, now: float) -> None:
    """Sunday's run is due but 30 ideas are already in trial: the watcher hears «skipped», not silence (once a day)."""
    d = datetime.fromtimestamp(now, ZoneInfo("UTC"))
    if d.weekday() != 6 or d.hour < 14 or now - float(db.get("ideas:last") or 0) < WEEK:
        return
    day = d.strftime("%Y-%m-%d")
    if db.get("hc:ideas_skip") != day:
        db.put("hc:ideas_skip", day)
        from . import heartbeat
        heartbeat.skip("hypothesis-weekly", f"{MAX_ACTIVE} fikir artıq sınaqdadır")


async def tick(db: DB, keys, now: float | None = None, activity=None) -> int:
    """Sunday, once a week: ask the brain, validate, register at most two ideas. Never raises."""
    import asyncio
    from . import brains, rules
    now = time.time() if now is None else now
    if not due(db, now):
        _weekly_skip(db, now)
        return 0
    db.put("ideas:last", str(now))
    from . import heartbeat
    heartbeat.beat("hypothesis-weekly", "ok", "həftəlik fikir axtarışı başladı")
    rep = activity.report if activity else (lambda *a, **k: None)
    rep("ideas", "working", "W1 Yaddaş", 0.2)
    rec = (await asyncio.to_thread(rules.records, db))["rules"]
    rep("ideas", "working", "W2 Beyin", 0.4)
    data, how = await brains.run(db, keys, "ideas", SYSTEM, await asyncio.to_thread(memory, db, rec), OUT_SCHEMA,
                                 max_tokens=1500)
    if data is None:
        rep("ideas", "error", note="beyin cavab vermədi: " + how)
        return 0
    rep("ideas", "working", "W3 Şablon", 0.7)
    added = 0
    for raw in (data.get("ideas") or [])[:PER_WEEK]:
        spec, why = validate(db, raw, rec)
        if spec is None:
            db.execute("INSERT INTO ideas(ts, base, tf, spec, why, expect, brain, status, reason) "
                       "VALUES(?,?,?,?,?,?,?,'rədd',?)", (now, str(raw.get("base"))[:40], str(raw.get("tf"))[:4],
                                                         json.dumps(raw, ensure_ascii=False)[:600],
                                                         str(raw.get("why"))[:400], str(raw.get("expect"))[:300],
                                                         how[:80], why))
            continue
        await asyncio.to_thread(add, db, spec, str(raw.get("why") or ""), str(raw.get("expect") or ""), how, now)
        added += 1
    rep("ideas", "done", note=f"{added} yeni fikir sınağa göndərildi")
    return added


def view(db: DB) -> list[dict]:
    """Every idea with its rule's record (the Judge's numbers) for the page."""
    ensure(db)
    return [dict(r) for r in db.execute("SELECT * FROM ideas ORDER BY id DESC LIMIT 60").fetchall()]
