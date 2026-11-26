"""Aralığın özü-özünə tənzimlənməsi (owner 2026-11-26, plan step 9: «first tested on the past, then live»).

The 80 % range already learns its width from past moves (forecast.range_quantiles). Adaptive conformal correction
(Gibbs & Candès 2021) adds one thing: when the range has recently missed more than 20 % of the time it widens a
little, when it has caught everything it narrows a little — so it stays at 80 % when the market changes character.
Multiplicative form: m <- m * exp(gamma * (miss - 0.20)), applied only once each outcome is known (no look-ahead);
gamma 0.02 for 1 hour / 4 hours, 0.01 for 1 day / 1 week (fixed in advance). Only the width changes, never the
direction.

This file is the test on the past (shadow): the headline range of each desk replayed with and without the
correction; coverage over the last 250 outcomes and the average width. Nothing reaches a live forecast here."""
from __future__ import annotations

import json
import math
import time

from .db import DB

GAMMA = {"1h": 0.02, "4h": 0.02, "1d": 0.01, "1w": 0.01}
TARGET_MISS = 0.20
M_BOUNDS = (0.5, 2.0)
LAST = 250
KEY = "aci:shadow"


def replay(rows: list) -> dict:
    """rows: (issued_t, target_t, price0, price1, lo80, hi80) oldest first, one per forecast moment."""
    m, pending = 1.0, []
    base_in, aci_in, widths = [], [], []
    gamma = None
    for r in rows:
        t = r["issued_t"]
        still = []
        for q in pending:                     # learn from the outcomes known by now
            if q[0] <= t:
                m = min(M_BOUNDS[1], max(M_BOUNDS[0], m * math.exp(gamma * ((0 if q[1] else 1) - TARGET_MISS))))
            else:
                still.append(q)
        pending = still
        p0, p1 = r["price0"], r["price1"]
        half = (r["hi80"] - r["lo80"]) / 2
        if half <= 0 or not p0:
            continue
        mid = (r["hi80"] + r["lo80"]) / 2
        base = r["lo80"] <= p1 <= r["hi80"]
        adj = abs(p1 - mid) <= half * m
        base_in.append(base)
        aci_in.append(adj)
        widths.append(m)
        gamma = gamma or r["gamma"]
        pending.append((r["target_t"], adj))
    def cov(xs):
        xs = xs[-LAST:]
        return round(sum(xs) / len(xs), 4) if xs else None
    return {"n": len(base_in), "now_cover": cov(base_in), "aci_cover": cov(aci_in),
            "now_cover_all": round(sum(base_in) / len(base_in), 4) if base_in else None,
            "aci_cover_all": round(sum(aci_in) / len(aci_in), 4) if aci_in else None,
            "aci_width": round(sum(widths[-LAST:]) / len(widths[-LAST:]), 3) if widths else None,
            "m_now": round(m, 3)}


def shadow(db: DB, symbols=("XAU", "XAG", "XPT", "XPD")) -> dict:
    t0 = time.time()
    out: dict = {"computed": None, "desks": {}}
    for s in symbols:
        for h, g in GAMMA.items():
            rows = db.execute("SELECT issued_t, target_t, price0, price1, lo80, hi80 FROM forecasts WHERE symbol=? AND "
                              "horizon=? AND method='rw' AND price1 IS NOT NULL ORDER BY issued_t DESC LIMIT 6000",
                              (s, h)).fetchall()
            rows = [{**dict(r), "gamma": g} for r in reversed(rows)]
            if rows:
                out["desks"][f"{s}:{h}"] = replay(rows)
    out["computed"] = time.time()
    out["seconds"] = round(time.time() - t0, 1)
    ok = [d for d in out["desks"].values() if d["aci_cover"] is not None and d["now_cover"] is not None]
    out["summary"] = {
        "desks": len(ok),
        "closer_to_80": sum(1 for d in ok if abs(d["aci_cover"] - 0.8) < abs(d["now_cover"] - 0.8)),
        "aci_in_77_83": sum(1 for d in ok if 0.77 <= d["aci_cover"] <= 0.83),
        "now_in_77_83": sum(1 for d in ok if 0.77 <= d["now_cover"] <= 0.83)}
    db.put(KEY, json.dumps(out))
    return out


def view(db: DB) -> dict | None:
    try:
        return json.loads(db.get(KEY) or "null")
    except ValueError:
        return None
