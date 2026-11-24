"""Sabah üçün proqnoz (owner 2026-11-24: «tomorrow I want to see: will it rise or fall, and on what basis»).

For each metal, one honest picture of the next day (the 1-day desk), from what the system already produces:
- the range: our 1-day 50 % and 80 % ranges and how often the 80 % range really held (the one proven skill);
- three voices on the direction, each with its own record:
  1. Strateq (the AI analyst): its 1-day probability, the reason, the counter-scenario, what would weaken it, when to
     renew (the frozen forecast card), and how its 1-day cards turned out so far;
  2. Tərəzi: the analysts weighted by the Judge (empty when the Judge trusts none yet);
  3. the analysts' vote: how many of the methods lean up / down right now;
- one line, ONE answer: the unified forecast's direction (the voices explain it; how many agree is shown);
- the proof status from the Judge for the 1-day desk. A lean is NOT a proven forecast: the page says so plainly.
Nothing here is invented: every number comes from the forecasts, the Judge or the cards."""
from __future__ import annotations

import time

from . import cards, judge
from .db import DB
from .forecast import BASELINES, METHOD_NAMES

H = "1d"
LEAN = 0.03          # a probability within 0.5 ± LEAN is «no view»


def _latest(db: DB, sym: str) -> dict:
    row = db.execute("SELECT MAX(issued_t) t FROM forecasts WHERE symbol=? AND horizon=? AND mode='live'",
                     (sym, H)).fetchone()
    if not row or row["t"] is None:
        return {}
    return {r["method"]: dict(r) for r in db.execute(
        "SELECT method, issued_t, target_t, price0, p_up, lo50, hi50, lo80, hi80, basis FROM forecasts "
        "WHERE symbol=? AND horizon=? AND mode='live' AND issued_t=?", (sym, H, row["t"])).fetchall()}


def _dir(p: float | None) -> int:
    if p is None or abs(p - 0.5) < LEAN:
        return 0
    return 1 if p > 0.5 else -1


def build(db: DB, sym: str) -> dict:
    fc = _latest(db, sym)
    st = {r["method"]: r for r in judge.stats(db, sym, H, "live", ttl=600)}
    hist = {r["method"]: r for r in judge.stats(db, sym, H, "history", ttl=600)}
    rw = fc.get("rw")
    out: dict = {"symbol": sym, "issued_t": rw["issued_t"] if rw else None, "target_t": rw["target_t"] if rw else None,
                 "price": rw["price0"] if rw else None}
    if rw:
        cov = (st.get("rw") or {}).get("cover80")
        if cov is None or (st.get("rw") or {}).get("n", 0) < 30:
            cov = (hist.get("rw") or {}).get("cover80")
        out["range"] = {"lo50": rw["lo50"], "hi50": rw["hi50"], "lo80": rw["lo80"], "hi80": rw["hi80"], "cover80": cov}
    # voice 1: Strateq's latest 1-day card
    card = next((c for c in cards.recent(db, sym, 40) if c["horizon"] == H), None)
    summ = cards.summary(db).get(f"strateq:{H}", {})
    if card:
        p = card["p_cal"] if card["p_cal"] is not None else card["p"]
        out["strateq"] = {"p": p, "calibrated": card["p_cal"] is not None, "ts": card["known_ts"],
                          "scenario": card["scenario"], "counter": card["counter"], "invalidation": card["invalidation"],
                          "next_update": card["next_update"], "quality": card["quality"],
                          "record": {"right": summ.get("düz", 0), "wrong": summ.get("səhv", 0)}}
    # voice 1b: the Chartist (AI reading the charts itself)
    import json as _json
    try:
        ch = _json.loads(db.get("chartist:last") or "null")
    except ValueError:
        ch = None
    cm = next((m for m in (ch or {}).get("metals", []) if m.get("symbol") == sym), None)
    if cm:
        out["chartist"] = {"p": cm.get("p1d"), "trend": cm.get("trend"), "levels": cm.get("levels"),
                           "pattern": cm.get("pattern"), "why": cm.get("why"), "ts": ch.get("ts")}
    # voice 2: the scale
    ter = fc.get("terazi")
    if ter:
        r = st.get("terazi") or {}
        out["terazi"] = {"p": ter["p_up"], "basis": ter["basis"], "n": r.get("nh"), "hit_rate": r.get("hit_rate"),
                         "bar": r.get("bar")}
    # the headline: the unified forecast (every analyst and brain in one probability, weights learned walk-forward)
    vh = fc.get("vahid")
    if vh:
        from . import unified
        mdl = unified.models(db).get(f"{sym}:{H}") or {}
        r = st.get("vahid") or {}
        out["vahid"] = {"p": vh["p_up"], "basis": vh["basis"], "self_test": {
            "n": mdl.get("viewed"), "hit_rate": mdl.get("hit_rate"), "bar": mdl.get("bar"), "bss": mdl.get("bss"),
            "net_avg": mdl.get("net_avg")}, "live": {"n": r.get("nh"), "hit_rate": r.get("hit_rate"),
                                                    "status": r.get("status")}}
    # voice 3: the analysts' vote (methods with a view, baselines and combiners left out)
    up, down, names_up, names_down = 0, 0, [], []
    for m, v in fc.items():
        if m in BASELINES or m in ("terazi", "consensus", "vahid"):
            continue
        d = _dir(v["p_up"])
        if d > 0:
            up += 1
            names_up.append(METHOD_NAMES.get(m, m))
        elif d < 0:
            down += 1
            names_down.append(METHOD_NAMES.get(m, m))
    out["vote"] = {"up": up, "down": down, "up_names": names_up[:8], "down_names": names_down[:8]}
    # ONE answer (2026-11-24, no contradiction): the line is the unified forecast's direction; the voices are its
    # explanation — how many of them agree with it is shown, but they never give a second «final» answer.
    vp = (out.get("vahid") or {}).get("p")
    lean = _dir(vp) if vp is not None else 0
    if vp is not None and lean == 0 and abs(vp - 0.5) >= 0.01:
        lean = 1 if vp > 0.5 else -1
        weak = True                                  # the unified view leans, but only a little
    else:
        weak = False
    voices = [d for d in (_dir((out.get("strateq") or {}).get("p")), _dir((out.get("terazi") or {}).get("p")),
                          _dir((out.get("chartist") or {}).get("p")),
                          (1 if up > down * 1.5 and up >= 3 else -1 if down > up * 1.5 and down >= 3 else 0)) if d]
    out["lean"] = ({1: "zəif yuxarı meyl", -1: "zəif aşağı meyl"} if weak else
                   {1: "yuxarı meyl", -1: "aşağı meyl", 0: "aydın deyil"})[lean]
    out["lean_dir"] = 0 if weak else lean
    out["weak_dir"] = lean if weak else 0
    out["agree"] = ("vahid proqnoz hələ yoxdur" if vp is None else
                    f"səslərdən {sum(1 for d in voices if d == lean)} razı, {sum(1 for d in voices if d == -lean)} əks"
                    if lean else f"{len(voices)} səsin fikri var, vahid nəticə: aydın deyil")
    verdict = judge.official(list(st.values()) if max((r.get("n") or 0) for r in st.values()) >= judge.MIN_N[H]
                             else list(hist.values())) if st else {"status": "az"}
    out["proof"] = verdict.get("status")
    out["cost"] = judge.full_cost(sym, H)
    return out


def all_metals(db: DB) -> dict:
    from .candles import METALS
    return {"ts": time.time(), "horizon": H, "metals": [build(db, s) for s in METALS]}
