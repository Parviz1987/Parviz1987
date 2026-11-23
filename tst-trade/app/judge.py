"""The Judge (Hakim): scores every forecast when its candle closes and says which method, if any, can be trusted.

Per forecast: outcome (1 up / 0 down; an unchanged close is not scored), hit (direction right; P = 0.5 has no
direction and gets no hit), Brier score, and whether the close fell inside the 50 % and 80 % ranges.
Per method: hit rate against «Həmişə yuxarı», Brier skill against a coin (0.25), range coverage, and a status:
- "az"      fewer scored forecasts than MIN_N: no verdict yet
- "sübut"   beats the better baseline on hit rate with one-sided p < 0.05 AND Brier skill > 0
- "yox"     enough forecasts, no proof of skill"""
from __future__ import annotations

import math
import time

from .db import DB
from .forecast import BASELINES, METHODS

MIN_N = {"1m": 300, "1h": 200, "1d": 250, "1w": 100}
P_MAX = 0.05


def issue(db: DB, symbol: str, horizon: str, issued_t: int, target_t: int, fc: dict, mode: str = "live") -> int:
    rows = [(symbol, horizon, m, mode, issued_t, target_t, fc["price"], v["p_up"], v["lo50"], v["hi50"],
             v["lo80"], v["hi80"], v["basis"]) for m, v in fc["methods"].items()]
    db.executemany(
        "INSERT OR IGNORE INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, "
        "lo50, hi50, lo80, hi80, basis) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def score_row(price0: float, price1: float, p_up: float, lo50: float, hi50: float, lo80: float, hi80: float) -> dict:
    in50 = int(lo50 <= price1 <= hi50)
    in80 = int(lo80 <= price1 <= hi80)
    if price1 == price0:
        return {"outcome": None, "hit": None, "brier": None, "in50": in50, "in80": in80}
    outcome = int(price1 > price0)
    hit = None if p_up == 0.5 else int((p_up > 0.5) == bool(outcome))
    return {"outcome": outcome, "hit": hit, "brier": (p_up - outcome) ** 2, "in50": in50, "in80": in80}


def score_due(db: DB, now: float | None = None) -> int:
    """Score every open forecast whose target candle has closed (one query joins each forecast to its candle)."""
    now = time.time() if now is None else now
    rows = db.execute(
        "SELECT f.id, f.target_t, f.price0, f.p_up, f.lo50, f.hi50, f.lo80, f.hi80, c.c AS close1 "
        # A horizon is named after the candle it is built from (forecast.HORIZONS: 1m->1m ...), so tf = horizon.
        "FROM forecasts f LEFT JOIN candles c ON c.symbol=f.symbol AND c.tf=f.horizon AND c.t=f.issued_t "
        "WHERE f.scored_ts IS NULL AND f.target_t <= ?", (now,)).fetchall()
    updates, dropped = [], []
    for r in rows:
        if r["close1"] is None:
            # No candle for the target (market closed, feed gap): dropped after a day, never guessed.
            if now - r["target_t"] > 86400:
                dropped.append((now, r["id"]))
            continue
        s = score_row(r["price0"], r["close1"], r["p_up"], r["lo50"], r["hi50"], r["lo80"], r["hi80"])
        updates.append((r["close1"], now, s["outcome"], s["hit"], s["brier"], s["in50"], s["in80"], r["id"]))
    if updates:
        db.executemany("UPDATE forecasts SET price1=?, scored_ts=?, outcome=?, hit=?, brier=?, in50=?, in80=? "
                       "WHERE id=?", updates)
    if dropped:
        db.executemany("UPDATE forecasts SET scored_ts=? WHERE id=?", dropped)
    return len(updates)


def _p_one_sided(hits: int, n: int, p0: float) -> float:
    """P(at least `hits` of n | true rate p0), normal approximation with continuity correction."""
    if n == 0 or p0 <= 0 or p0 >= 1:
        return 1.0
    z = (hits - 0.5 - n * p0) / math.sqrt(n * p0 * (1 - p0))
    return 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))


def stats(db: DB, symbol: str, horizon: str, mode: str = "live") -> list[dict]:
    q = ("SELECT method, COUNT(outcome) n, SUM(outcome) ups, COUNT(hit) nh, SUM(hit) hits, AVG(brier) brier, "
         "AVG(in50) c50, AVG(in80) c80, COUNT(price1) ncov FROM forecasts "
         "WHERE symbol=? AND horizon=? AND mode=? AND scored_ts IS NOT NULL GROUP BY method")
    rows = {r["method"]: dict(r) for r in db.execute(q, (symbol, horizon, mode)).fetchall()}
    base_up = rows.get("up", {})
    up_rate = (base_up.get("ups") or 0) / base_up["n"] if base_up.get("n") else None
    out = []
    for m in METHODS:
        r = rows.get(m) or {"n": 0, "nh": 0, "hits": 0, "brier": None, "c50": None, "c80": None}
        n, nh, hits = r["n"] or 0, r["nh"] or 0, r["hits"] or 0
        hit_rate = hits / nh if nh else None
        bss = 1 - r["brier"] / 0.25 if r["brier"] is not None else None
        # Beat the better of a coin (0.5) and «always up» on the same forecasts.
        bar = max(0.5, up_rate if up_rate is not None else 0.5, 1 - (up_rate or 0.5))
        p = _p_one_sided(hits, nh, bar) if nh else None
        if m in BASELINES:
            status = "bazis"
        elif n < MIN_N[horizon]:
            status = "az"
        elif p is not None and p < P_MAX and bss is not None and bss > 0:
            status = "sübut"
        else:
            status = "yox"
        out.append({"method": m, "n": n, "hit_rate": hit_rate, "bar": bar, "p": p, "brier": r["brier"],
                    "bss": bss, "cover50": r["c50"], "cover80": r["c80"], "status": status,
                    "min_n": MIN_N[horizon]})
    return out


def official(stat_rows: list[dict]) -> dict:
    """The card's verdict: the proven method with the best Brier skill, or none."""
    proven = [r for r in stat_rows if r["status"] == "sübut"]
    if proven:
        best = max(proven, key=lambda r: r["bss"])
        return {"method": best["method"], "status": "sübut"}
    if any(r["status"] == "yox" for r in stat_rows):
        return {"method": "rw", "status": "yox"}
    return {"method": "rw", "status": "az"}
