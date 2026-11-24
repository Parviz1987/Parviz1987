"""Fyuçers sınaqları (Block 21, Stage 2): the owner's ideas tested on two years of COMEX one-minute bars (Databento).

Design written BEFORE the data was seen (2026-11-24), so it cannot be tuned to it:
1. Data check: bars per metal, first/last day, missing minutes inside trading hours.
2. Impulse (the owner's idea): a minute that moves >= K x its usual move (exponential average of PAST minutes only)
   and >= a floor. We act a minute late: entry at the close of the next minute, exit H minutes later (5, 15, 30, 60).
   «Continues» = the exit is further in the impulse's direction. Split by the minute's VOLUME against its usual volume
   (>= 3x = «böyük oyunçu», heavy) — real volume is what the broker's data never had.
3. News (scheduled US releases): impulses that start in the release minutes 08:30, 10:00 or 14:00 New York time.
   The same test, separately: does the move after a release go on once we can act?
4. Costs: futures = one tick spread + half a tick slippage (no overnight fee: minutes); shown next to what the same
   trade would cost on Capital (judge.full_cost) — where is it cheaper to act.
5. Robustness: every result also by year (first year / second year). A result is only «sübut» if the hit rate beats
   0.5 at p < 0.05 / (number of cells), the net result after cost is > 0, and it holds in BOTH years.
Impulses within 30 minutes of the previous one are skipped (one move, one test). Read-only: nothing trades."""
from __future__ import annotations

import json
import math
import time
from array import array
from datetime import datetime
from zoneinfo import ZoneInfo

from .db import DB
from .futures import SYMBOLS, TICK

KS = (4.0, 6.0)
HS = (5, 15, 30, 60)
FLOOR = {"XAU": 0.0003, "XAG": 0.0006, "XPT": 0.0006, "XPD": 0.0008}
GAP = 30
HEAVY = 3.0
NEWS_MIN = {(8, 30), (10, 0), (14, 0)}
NY = ZoneInfo("America/New_York")


def _p_two(hits: int, n: int) -> float | None:
    if n < 10:
        return None
    z = (hits - n / 2) / math.sqrt(n / 4)
    return 1 - math.erf(abs(z) / math.sqrt(2))


def _load(db: DB, sym: str):
    ts, cs, vs = array("q"), array("d"), array("d")
    for r in db.execute("SELECT t, c, v FROM fut_candles WHERE symbol=? ORDER BY t", (sym,)):
        ts.append(int(r["t"]))
        cs.append(float(r["c"]))
        vs.append(float(r["v"] or 0))
    return ts, cs, vs


def check(db: DB) -> dict:
    out = {}
    for sym in SYMBOLS:
        r = db.execute("SELECT COUNT(*) n, MIN(t) a, MAX(t) b FROM fut_candles WHERE symbol=?", (sym,)).fetchone()
        if not r["n"]:
            out[sym] = {"n": 0}
            continue
        # gaps of 2..30 minutes inside the session (longer = the daily break or a weekend, not missing data)
        gaps = db.execute("SELECT COUNT(*) g FROM (SELECT t - LAG(t) OVER (ORDER BY t) d FROM fut_candles "
                          "WHERE symbol=?) WHERE d BETWEEN 120 AND 1800", (sym,)).fetchone()["g"]
        out[sym] = {"n": r["n"], "first": time.strftime("%Y-%m-%d", time.gmtime(r["a"])),
                    "last": time.strftime("%Y-%m-%d", time.gmtime(r["b"])), "short_gaps": gaps}
    return out


def study(db: DB) -> dict:
    from .judge import full_cost
    out: dict = {"computed": time.time(), "check": check(db), "metals": {}}
    cells = 0
    raw: dict = {}
    for sym in SYMBOLS:
        ts, cs, vs = _load(db, sym)
        n = len(ts)
        if n < 5000:
            continue
        idx = {t: i for i, t in enumerate(ts)}
        mid = ts[0] + (ts[-1] - ts[0]) // 2
        fut_cost = 1.5 * TICK[sym] / (sum(cs[-1000:]) / min(1000, n))
        cap_cost = full_cost(sym)
        ew = ewv = None
        last = -10 ** 9
        res: dict = {}
        for i in range(1, n - 1):
            if ts[i] - ts[i - 1] != 60 or not cs[i - 1]:
                continue
            r = cs[i] / cs[i - 1] - 1
            a = abs(r)
            usual, usual_v = ew, ewv
            ew = a if ew is None else ew + (a - ew) / 240
            ewv = vs[i] if ewv is None else ewv + (vs[i] - ewv) / 240
            if not usual or i - last < GAP:
                continue
            if a < max(KS[0] * usual, FLOOR[sym]):
                continue
            last = i
            heavy = "böyük həcm" if usual_v and vs[i] >= HEAVY * usual_v else "adi həcm"
            loc = datetime.fromtimestamp(ts[i], NY)
            news = (loc.hour, loc.minute) in NEWS_MIN
            year = "1-ci il" if ts[i] < mid else "2-ci il"
            j0 = i + 1
            if j0 >= n or ts[j0] != ts[i] + 60:
                continue
            for K in KS:
                if a < max(K * usual, FLOOR[sym]):
                    continue
                for H in HS:
                    j1 = idx.get(ts[i] + 60 * (1 + H))
                    if j1 is None:
                        continue
                    move = cs[j1] / cs[j0] - 1
                    gain = move if r > 0 else -move
                    cont = move != 0 and (move > 0) == (r > 0)
                    groups = ["hamısı", heavy] + (["xəbər dəqiqəsi"] if news else [])
                    for g in groups:
                        for part in ("cəmi", year):
                            res.setdefault((K, H, g, part), []).append((cont, gain))
        rows = []
        for (K, H, g, part), v in sorted(res.items()):
            m = len(v)
            hits = sum(c for c, _ in v)
            gross = sum(x for _, x in v) / m
            rows.append({"K": K, "H": H, "group": g, "part": part, "n": m, "continues": round(hits / m, 3),
                         "p": None if _p_two(hits, m) is None else round(_p_two(hits, m), 5),
                         "net_futures": round(gross - fut_cost, 6), "net_capital": round(gross - cap_cost, 6)})
            if part == "cəmi":
                cells += 1
        raw[sym] = rows
        out["metals"][sym] = {"bars": n, "cost_futures": round(fut_cost, 6), "cost_capital": round(cap_cost, 6)}
    p_bar = 0.05 / max(1, cells)
    out["p_bar"] = p_bar
    for sym, rows in raw.items():
        by = {(x["K"], x["H"], x["group"], x["part"]): x for x in rows}
        for x in rows:
            if x["part"] != "cəmi":
                continue
            y1, y2 = by.get((x["K"], x["H"], x["group"], "1-ci il")), by.get((x["K"], x["H"], x["group"], "2-ci il"))
            both = bool(y1 and y2 and y1["net_futures"] > 0 and y2["net_futures"] > 0 and y1["continues"] > 0.5
                        and y2["continues"] > 0.5)
            x["both_years"] = both
            x["verdict"] = ("az" if x["n"] < 100 else
                            "sübut" if x["p"] is not None and x["p"] < p_bar and x["continues"] > 0.5
                            and x["net_futures"] > 0 and both else "yox")
        out["metals"][sym]["rows"] = rows
    return out


def run_and_store(db: DB) -> dict:
    res = study(db)
    db.put("futstudy:last", json.dumps(res, ensure_ascii=False))
    return res


def summary(db: DB) -> dict | None:
    """The short version for the page: per metal the best (and the proven) cells over the whole period."""
    try:
        res = json.loads(db.get("futstudy:last") or "null")
    except ValueError:
        return None
    if not res:
        return None
    short = {"computed": res["computed"], "check": res["check"], "p_bar": res.get("p_bar"), "metals": {}}
    for sym, m in res["metals"].items():
        rows = [x for x in m.get("rows", []) if x["part"] == "cəmi"]
        short["metals"][sym] = {"bars": m["bars"], "cost_futures": m["cost_futures"], "cost_capital": m["cost_capital"],
                                "proven": [x for x in rows if x.get("verdict") == "sübut"],
                                "rows": [x for x in rows if x["K"] == 4.0]}
    return short
