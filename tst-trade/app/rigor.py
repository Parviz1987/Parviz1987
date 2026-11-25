"""Sübutun dürüstlüyü (owner 2026-11-25, from the Radar Gold design: «an untouched final period looked at once; count
every attempt»).

1. Cəhd sayğacı — every idea the system has ever tried counts: each method on each desk (metal x horizon), each rule
   on each timeframe, each registered hypothesis, also the retired ones (a set that only grows). A proof is shown next
   to how many attempts it was selected from, with the Šidák-adjusted p: p_all = 1 - (1 - p)^N — the chance that the
   best of N attempts looks this good by luck alone.
2. Son sınaq (one look) — a method or rule that reaches «sübut» becomes a FINALIST at that moment. Its final test uses
   only what happened AFTER that moment (data nobody could have looked at while choosing it), once, when enough cases
   exist; the verdict is stored for good and never recomputed. The Judge's «sübut» (and so any AL / SAT) requires a
   passed final test; until then the status is «namizəd» (candidate).
Nothing here makes a forecast; it only decides how much a result may be trusted."""
from __future__ import annotations

import json
import math
import time

from .db import DB

ALPHA = 0.05
RULE_MIN = 100            # rule finals: cases after the finalist moment


def _seen(db: DB) -> set[str]:
    try:
        return set(json.loads(db.get("trials:seen") or "[]"))
    except ValueError:
        return set()


def trials(db: DB) -> int:
    """The number of attempts ever made (it only grows: a retired idea still counts)."""
    from . import candles, forecast, hypotheses, playbook, rules
    seen = _seen(db)
    for m in list(forecast.METHODS) + list(getattr(forecast, "RETIRED", ())):
        for h in forecast.HORIZONS:
            for s in candles.METALS:
                seen.add(f"m:{m}:{h}:{s}")
    for r in playbook.RULES:
        if r["detector"]:
            for tf in rules.TFS:
                seen.add(f"r:{r['id']}:{tf}")
    for group in ("HYPOTHESES", "FOCUS", "V_TESTS"):
        for x in getattr(hypotheses, group, []) or []:
            if isinstance(x, dict) and x.get("id"):
                seen.add(f"h:{x['id']}")
    db.put("trials:seen", json.dumps(sorted(seen)))
    return len(seen)


def p_all(p: float | None, n: int) -> float | None:
    """Šidák: the chance that at least one of n independent tries reaches p by luck."""
    if p is None:
        return None
    return 1 - (1 - min(max(p, 0.0), 1.0)) ** max(1, n)


# ---------- the one-look final test ----------
def _key(kind: str, sym: str, h: str, name: str) -> str:
    return f"final:{kind}:{sym}:{h}:{name}"


def _money_test(rets: list[float], cost: float, k: int) -> tuple[float | None, float | None]:
    """Mean result after cost and the one-sided p (overlap-corrected: n / k independent cases), as the Judge does."""
    n = len(rets)
    if n < 2:
        return None, None
    mean = sum(rets) / n
    var = max(sum((x - mean) ** 2 for x in rets) / (n - 1), 1e-18)
    t = (mean - cost) / math.sqrt(var / max(1.0, n / k))
    return mean - cost, 1 - 0.5 * (1 + math.erf(t / math.sqrt(2)))


def method_final(db: DB, sym: str, horizon: str, method: str, now: float | None = None) -> dict:
    """The final state of a proven method on a desk: registers the finalist moment the first time, then tests once."""
    from .forecast import steps_of
    from .judge import MIN_N, full_cost
    now = time.time() if now is None else now
    key = _key("m", sym, horizon, method)
    st = json.loads(db.get(key) or "null")
    if st is None:
        st = {"since": now, "status": "namizəd"}
        db.put(key, json.dumps(st))
    if st["status"] in ("keçdi", "keçmədi"):
        return st                                  # looked at once: never again
    rows = db.execute("SELECT p_up, price0, price1 FROM forecasts WHERE symbol=? AND horizon=? AND method=? AND "
                      "mode='live' AND issued_t > ? AND price1 IS NOT NULL AND p_up != 0.5", (sym, horizon, method,
                                                                                            st["since"])).fetchall()
    need = MIN_N.get(horizon, 100)
    st["n"], st["need"] = len(rows), need
    if len(rows) < need:
        db.put(key, json.dumps(st))
        return st
    rets = [(r["price1"] / r["price0"] - 1) * (1 if r["p_up"] > 0.5 else -1) for r in rows if r["price0"]]
    net, p = _money_test(rets, full_cost(sym, horizon), steps_of(horizon))
    st.update({"status": "keçdi" if p is not None and p < ALPHA and net > 0 else "keçmədi", "p": p, "net": net,
               "tested": now})
    db.put(key, json.dumps(st))
    return st


def rule_final(db: DB, rule: str, tf: str, now: float | None = None) -> dict:
    """The same for a Bilik kitabı rule (all metals together, net of each metal's cost)."""
    from .judge import full_cost
    now = time.time() if now is None else now
    key = _key("r", "*", tf, rule)
    st = json.loads(db.get(key) or "null")
    if st is None:
        st = {"since": now, "status": "namizəd"}
        db.put(key, json.dumps(st))
    if st["status"] in ("keçdi", "keçmədi"):
        return st
    rows = db.execute("SELECT metal, dir, price0, price1 FROM rule_signals WHERE rule=? AND tf=? AND t > ? AND "
                      "price1 IS NOT NULL AND price0 > 0 AND mode != 'futures'", (rule, tf, st["since"])).fetchall()
    st["n"], st["need"] = len(rows), RULE_MIN
    if len(rows) < RULE_MIN:
        db.put(key, json.dumps(st))
        return st
    nets = [(r["price1"] / r["price0"] - 1) * r["dir"] - full_cost(r["metal"], tf) for r in rows]
    net, p = _money_test(nets, 0.0, 1)
    st.update({"status": "keçdi" if p is not None and p < ALPHA and net > 0 else "keçmədi", "p": p, "net": net,
               "tested": now})
    db.put(key, json.dumps(st))
    return st


def finals(db: DB) -> list[dict]:
    """Every finalist and its state (for the pages and the weekly report)."""
    out = []
    for r in db.execute("SELECT k, v FROM kv WHERE k LIKE 'final:%' ORDER BY k").fetchall():
        _, kind, sym, h, name = r["k"].split(":", 4)
        out.append({"kind": "üsul" if kind == "m" else "qayda", "symbol": sym, "horizon": h, "name": name,
                    **json.loads(r["v"])})
    return out
