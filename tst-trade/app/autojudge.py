"""Avtomatik Hakim siyasəti (owner 2026-11-26: «Təsdiqləyirəm, qur» — the policy is approved ONCE; after that the Judge
decides by itself and asks the owner only for real money and for changing this policy). This file is protected.

Built on the research of 2026-11-26 (docs/research): bank model-risk rules approve a framework, not each decision
(SR 26-2, PRA SS1/23); Kayenta scores a canary 0–100 and promotes / rolls back by itself; Uber ramps new models from
shadow to a small slice; Google's ML Test Score takes the WEAKEST section as the score; forecasting centres always
publish and let verification set weights (Good Judgment, ECMWF); Grinold shrinks low-skill forecasts; half Kelly
gives up about a quarter of the growth for far smaller drawdowns; SEC 15c3-5 / MiFID RTS 6: automatic limits and a
kill switch instead of a human per decision; Anthropic / OpenAI agents: act inside pre-approved bounds, escalate only
irreversible or money actions.

1. A score 0–100 per method and desk = the WEAKEST of five parts: result after the full cost (t 0 → 0, t 3 → 100),
   skill against the market's own lean (Brier skill 0 → 0, 0.02 → 100), stability (both halves of the record net
   positive → 100, one → 50), the amount of evidence (independent cases / the desk's minimum), and the Deflated
   Sharpe (× 100).
2. The ladder, decided by the score alone: < 50 off; 50–70 shadow (forecasts only); 70–85 small paper share (a
   quarter of the normal risk); ≥ 85 AND the one-look final test passed → full paper share. Re-scored every hour, so
   a method that weakens steps down by itself.
3. The size: half Kelly of the method's own record (mean / variance of its net result), times score / 100, never more
   than 25 % of the paper account in one method. A likely-right method is used a little before it is proven.
4. Real money: never — that stays the owner's choice."""
from __future__ import annotations

import json
import math
import time

from .db import DB

OFF, SHADOW, SMALL, FULL = "söndürülüb", "kölgə", "kiçik kağız payı", "tam kağız payı"
CUT_SHADOW, CUT_SMALL, CUT_FULL = 50, 70, 85
SMALL_FACTOR = 0.25
MAX_SHARE = 0.25           # of the paper account, per method
KEY = "autojudge:scores"


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


RECENT = 100               # independent cases in the «recent» score (a method that decays steps down quickly)


def skill_vs_lean(ps: list[float], ys: list[int]) -> float | None:
    """Brier skill against the market's own lean (a constant forecast of its up share), not against a coin: in a
    rising market leaning long is no skill."""
    if len(ps) < 30:
        return None
    base = sum(ys) / len(ys)
    b = sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)
    b0 = sum((base - y) ** 2 for y in ys) / len(ys)
    return 1 - b / b0 if b0 > 0 else None


def score_method(nets: list[float], bss: float | None, k: int, min_n: int, n_trials: int) -> dict:
    """The five parts and the weakest of them (all from the method's live after-cost record on one desk). `min_n`
    counts independent cases; overlapping horizons count n / k."""
    from . import judgeplus
    n = len(nets)
    t = judgeplus.t_stat(nets, k) if n >= 3 else None
    half = n // 2
    halves = [sum(nets[:half]) > 0, sum(nets[half:]) > 0] if n >= 20 else [False, False]
    d = judgeplus.dsr(nets, n_trials, None, k) if n >= 30 * k else None
    parts = {"nəticə": _clip((t or 0) / 3 * 100), "bacarıq": _clip((bss or 0) / 0.02 * 100),
             "sabitlik": 100.0 if all(halves) else 50.0 if any(halves) else 0.0,
             "sübut həcmi": _clip(n / max(1, k) / max(1, min_n) * 100),
             "DSR": _clip((d or 0) * 100)}
    weakest = min(parts, key=parts.get)
    mu = sum(nets) / n if n else 0.0
    var = sum((x - mu) ** 2 for x in nets) / (n - 1) if n > 1 else 0.0
    kelly = mu / var if var > 0 and mu > 0 else 0.0
    return {"score": round(parts[weakest]), "parts": {k_: round(v) for k_, v in parts.items()}, "weakest": weakest,
            "t": t, "dsr": d, "kelly": kelly, "n": n}


def stage(score: float, final_passed: bool) -> str:
    if score >= CUT_FULL and final_passed:
        return FULL
    if score >= CUT_SMALL:
        return SMALL
    if score >= CUT_SHADOW:
        return SHADOW
    return OFF


def size_factor(st: str, sc: float, kelly: float) -> float:
    """The share of the normal paper risk budget: the ladder step x score / 100 (0 when the record is not positive)."""
    if st not in (SMALL, FULL) or kelly <= 0:
        return 0.0
    return round((SMALL_FACTOR if st == SMALL else 1.0) * sc / 100, 4)


def exposure_cap(kelly: float) -> float:
    """The most of the paper account one method may hold at once: half Kelly of its own record, never above 25 %."""
    return max(0.0, min(MAX_SHARE, 0.5 * kelly))


def refresh(db: DB, now: float | None = None) -> dict:
    """Every hour: score every method on every desk from its live record; store the ladder."""
    from . import forecast, judge, rigor
    from .candles import METALS
    now = time.time() if now is None else now
    try:
        n_trials = rigor.trials(db)
    except Exception:
        n_trials = 1000
    out: dict = {"computed": now, "desks": {}}
    for s in METALS:
        for h in forecast.HORIZONS:
            try:
                rows = judge.stats(db, s, h, "live", ttl=600)
            except Exception:
                continue
            cost = judge.full_cost(s, h)
            k = forecast.steps_of(h)
            min_n = judge.MIN_N.get(h, 100)
            desk = {}
            for r in rows:
                m = r["method"]
                if not judge.is_candidate(m, h):
                    continue
                q = db.execute("SELECT p_up, price0, price1 FROM forecasts WHERE symbol=? AND horizon=? AND method=? AND "
                               "mode='live' AND price1 IS NOT NULL AND price0 > 0 AND p_up != 0.5 ORDER BY issued_t "
                               "DESC LIMIT ?", (s, h, m, 4000 * max(1, k))).fetchall()[::-1]
                nets = [(x["price1"] / x["price0"] - 1) * (1 if x["p_up"] > 0.5 else -1) - cost for x in q]
                if len(nets) < 10:
                    continue
                ys = [int(x["price1"] > x["price0"]) for x in q]
                bss_lean = skill_vs_lean([x["p_up"] for x in q], ys)
                sc = score_method(nets, bss_lean, k, min_n, n_trials)
                recent = nets[-RECENT * k:]
                if len(recent) >= 30 * k and len(recent) < len(nets):   # the recent record can only lower it
                    rc = score_method(recent, skill_vs_lean([x["p_up"] for x in q[-RECENT * k:]], ys[-RECENT * k:]),
                                      k, RECENT, n_trials)
                    rc["parts"]["sübut həcmi"] = 100                    # the recent window is short by design
                    rscore = min(rc["parts"].values())
                    if rscore < sc["score"]:
                        sc = {**sc, "score": round(rscore), "weakest": "son " + str(RECENT) + " hal: " +
                              min(rc["parts"], key=rc["parts"].get)}
                fin = json.loads(db.get(f"final:m:{s}:{h}:{m}") or "{}")
                reg = rigor.registry_status(db, "method", m, s, h)
                st = stage(sc["score"], fin.get("status") == "keçdi")
                if reg in ("rədd edilib", "kölgəyə qaytarıldı") or fin.get("status") == "keçmədi" or fin.get("too_good"):
                    st = OFF                    # vetoes: the owner's rejection, a demotion, a failed or suspect final
                desk[m] = {**sc, "stage": st, "size": size_factor(st, sc["score"], sc["kelly"]),
                           "cap": exposure_cap(sc["kelly"]), "final": fin.get("status")}
            if desk:
                out["desks"][f"{s}:{h}"] = desk
    db.put(KEY, json.dumps(out, ensure_ascii=False))
    return out


def best(db: DB, symbol: str, horizon: str) -> tuple[str, dict] | None:
    """The desk's highest-scoring method that may trade on paper now (small or full share)."""
    try:
        d = (json.loads(db.get(KEY) or "{}").get("desks") or {}).get(f"{symbol}:{horizon}") or {}
    except ValueError:
        return None
    ok = [(v["score"], m, v) for m, v in d.items() if v.get("stage") in (SMALL, FULL) and v.get("size", 0) > 0]
    if not ok:
        return None
    _, m, v = max(ok)
    return m, v


def view(db: DB) -> dict | None:
    try:
        v = json.loads(db.get(KEY) or "null")
    except ValueError:
        return None
    if not v:
        return None
    count = {OFF: 0, SHADOW: 0, SMALL: 0, FULL: 0}
    for d in v.get("desks", {}).values():
        for x in d.values():
            count[x["stage"]] = count.get(x["stage"], 0) + 1
    return {"computed": v.get("computed"), "ladder": count,
            "top": sorted(((x["score"], f"{k}:{m}", x["stage"], x["weakest"]) for k, d in v.get("desks", {}).items()
                           for m, x in d.items()), reverse=True)[:10]}
