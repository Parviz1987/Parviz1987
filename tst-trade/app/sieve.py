"""The sieve and the journal (owner 2026-11-27: «hazırda bir laboratoriya kimi təcrübələr gedir; kim nə deyib, nəyə
əsasən, nə vaxt, düz olub, nə qədər düz olub — hamısını bilib sonra süzgəcdən keçirəcəyik, sistem sadə olsun»).

The journal: every call an analyst made (a forecast that took a side), with its basis, time, start and end price, how
far the price went in the direction it said, and whether it came true. Read straight from the forecasts table.

The sieve: every analyst sorted by FIXED rules (written here once, never tuned to a result), on the Judge's own
numbers (judge.stats: hit rate, the no-skill bar, the number of calls with a side, the Judge's status), live and on
the replayed history, every horizon, all four metals:
  saxla    the Judge found proof somewhere, or a real but too small edge («sübut» / «xərc»): keep and watch
  ümidli   on some horizon, with at least 100 independent calls, better than the bar by two standard errors, nowhere
           worse: not proof (many horizons are looked at), the place to watch
  qarışıq  better there, worse elsewhere: keep only where it is better (a candidate for a narrower job)
  pis      worse than the bar by two standard errors somewhere, nowhere better: it points the wrong way consistently:
           a removal candidate
  fərqsiz  at least 100 independent calls somewhere and never better or worse than chance: it adds noise, not
           information: a removal candidate (the owner wants a simple system)
  az       too few calls yet
Overlapping horizons (3 days, 10 days, 1 month: a forecast every day, each spanning k days) count n / k independent
calls. Removing an analyst stays the owner's decision; this only lists who is where."""
from __future__ import annotations

import math

from . import forecast, judge
from .db import DB

METALS = ("XAU", "XAG", "XPT", "XPD")
MIN_N = 100
Z_BAD = -2.0
NOT_ANALYSTS = ("rw",)          # «no change»: the range baseline, it never takes a side


def sieve(db: DB) -> dict:
    agg: dict = {}
    for mode in ("live", "history"):
        for h, (_tf, k) in forecast.HORIZON_SPEC.items():
            for s in METALS:
                for r in judge.stats(db, s, h, mode, ttl=600):
                    m = r["method"]
                    if m in NOT_ANALYSTS or not r.get("nh") or r.get("hit_rate") is None:
                        continue
                    a = agg.setdefault(m, {"cells": {}, "statuses": set()})
                    a["statuses"].add(r.get("status"))
                    c = a["cells"].setdefault((h, mode), {"nh": 0, "hits": 0.0, "bar": 0.0, "edge": 0.0, "k": k})
                    c["nh"] += r["nh"]
                    c["hits"] += r["hit_rate"] * r["nh"]
                    c["bar"] += (r.get("bar") or 0.5) * r["nh"]
                    c["edge"] += (r.get("edge") or 0.0) * r["nh"]
    rows = []
    for m, a in agg.items():
        cells = []
        for (h, mode), c in a["cells"].items():
            hit, bar = c["hits"] / c["nh"], c["bar"] / c["nh"]
            n_eff = c["nh"] / c["k"]
            z = (hit - bar) / math.sqrt(max(bar * (1 - bar), 1e-9) / n_eff)
            cells.append({"horizon": h, "mode": mode, "n": c["nh"], "n_eff": round(n_eff), "hit": round(hit, 4),
                          "bar": round(bar, 4), "z": round(z, 2), "edge": c["edge"] / c["nh"]})
        big = [c for c in cells if c["n_eff"] >= MIN_N]
        good, bad = any(c["z"] >= -Z_BAD for c in big), any(c["z"] <= Z_BAD for c in big)
        if a["statuses"] & {"sübut", "xərc"}:
            verdict = "saxla"
        elif good and bad:
            verdict = "qarışıq"
        elif good:
            verdict = "ümidli"
        elif bad:
            verdict = "pis"
        elif big:
            verdict = "fərqsiz"
        else:
            verdict = "az"
        pool = big or cells
        rows.append({"method": m, "name": forecast.METHOD_NAMES.get(m, m), "family": forecast.FAMILY.get(m),
                     "retired": m in forecast.RETIRED, "baseline": m == "up", "verdict": verdict,
                     "best": max(pool, key=lambda c: c["z"]) if pool else None,
                     "worst": min(pool, key=lambda c: c["z"]) if pool else None,
                     "calls": sum(c["n"] for c in cells), "cells": cells})
    order = {"saxla": 0, "ümidli": 1, "qarışıq": 2, "pis": 3, "fərqsiz": 4, "az": 5}
    rows.sort(key=lambda r: (r["retired"], r["baseline"], order[r["verdict"]], -r["calls"]))
    return {"rows": rows, "rules": {"min_n": MIN_N, "z_bad": Z_BAD}, "families": forecast.FAMILY_NAMES}


LAST = 10                       # the latest results kept per cell, newest first («düz ardıcıllığı»)


def _run(seq: str) -> int:
    """The current run, newest first: +3 = the last three came true, -2 = the last two did not."""
    if not seq:
        return 0
    k = len(seq) - len(seq.lstrip(seq[0]))
    return k if seq[0] == "1" else -k


def record(db: DB, days: int | None = None, now: float | None = None) -> dict:
    """The record book (owner 2026-11-27: «Əhməd qızılda düz deyir, gümüşdə səhv — Əhmədin qızılını gətirmək olar,
    gümüşünü yox; jurnalda kim harada nə deyib və düz deyib, düz ardıcıllığı»): for every analyst, every metal and every
    horizon, the live calls that took a side and were checked: how many, how many came true, the latest ten results
    (newest first, «1» right, «0» wrong) and the current run. Plain counts, no weighting: the Judge does the proof.
    days: only calls checked in the last N days (None: since the start)."""
    import time as _t
    since = 0 if not days else int((now or _t.time()) - days * 86400)
    out: dict = {}
    for s in METALS:
        for h in forecast.HORIZON_SPEC:
            rows = db.execute("SELECT method, hit, target_t FROM forecasts WHERE symbol=? AND horizon=? AND mode='live' "
                              "AND hit IS NOT NULL AND outcome IS NOT NULL AND target_t>=? "
                              "ORDER BY target_t DESC", (s, h, since)).fetchall()
            for r in rows:
                m = r["method"]
                if m in NOT_ANALYSTS:
                    continue
                per = out.setdefault(m, {}).setdefault(s, {})
                for key in (h, "all"):
                    c = per.setdefault(key, {"n": 0, "right": 0, "seq": []})
                    c["n"] += 1
                    c["right"] += r["hit"]
                    if key == h and len(c["seq"]) < LAST:
                        c["seq"].append((r["target_t"], r["hit"]))
                    elif key == "all":
                        c["seq"].append((r["target_t"], r["hit"]))
                        c["seq"].sort(key=lambda x: -x[0])
                        del c["seq"][LAST:]
    for per in out.values():
        for cells in per.values():
            for c in cells.values():
                last = "".join(str(int(hit)) for _t0, hit in c.pop("seq"))
                c["last"], c["streak"] = last, _run(last)
    names = {m: forecast.METHOD_NAMES.get(m, m) for m in out}
    return {"methods": out, "names": names, "family": {m: forecast.FAMILY.get(m) for m in out},
            "families": forecast.FAMILY_NAMES, "retired": [m for m in out if m in forecast.RETIRED],
            "horizons": list(forecast.HORIZON_SPEC), "horizon_names": forecast.HORIZON_NAMES, "days": days}


def calls(db: DB, method: str, symbol: str = "ALL", limit: int = 60, mode: str = "live",
          horizon: str | None = None) -> list[dict]:
    """The analyst's latest calls (the newest said first): what it said, why, when, and what happened."""
    syms = METALS if symbol == "ALL" else (symbol,)
    hs = (horizon,) if horizon in forecast.HORIZON_SPEC else tuple(forecast.HORIZON_SPEC)
    rows = []
    for s in syms:
        for h in hs:
            rows += db.execute("SELECT symbol, horizon, issued_t, target_t, p_up, basis, price0, price1, hit, in80, scored_ts "
                               "FROM forecasts WHERE symbol=? AND horizon=? AND mode=? AND method=? AND p_up != 0.5 "
                               "ORDER BY target_t DESC LIMIT ?", (s, h, mode, method, limit)).fetchall()
    rows.sort(key=lambda r: (r["issued_t"], r["target_t"]), reverse=True)     # newest said first
    out = []
    for r in rows[:limit]:
        up = r["p_up"] > 0.5
        move = None if r["price1"] is None or not r["price0"] else (r["price1"] / r["price0"] - 1) * (1 if up else -1) * 100
        out.append({"symbol": r["symbol"], "horizon": r["horizon"], "issued_t": r["issued_t"], "target_t": r["target_t"],
                    "said": "yuxarı" if up else "aşağı", "p": round(r["p_up"] if up else 1 - r["p_up"], 3),
                    "basis": r["basis"], "price0": r["price0"], "price1": r["price1"],
                    "right": None if r["hit"] is None else bool(r["hit"]),
                    "in80": None if r["in80"] is None else bool(r["in80"]), "move_pct": move,
                    "checked": r["scored_ts"] is not None})
    return out
