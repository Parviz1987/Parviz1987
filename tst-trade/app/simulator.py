"""Shadow trading (kölgə ticarəti): every forecast with a direction played as a real trade, on paper, and measured in
money after costs. The Judge asks «how often is the direction right?»; this asks «would it have made money?» — the
question that decides trading. A method right 45 % of the time can still earn (small losses, big wins) and one right
55 % can still lose.

Rules of one trade (the same for every method, fixed in advance, never tuned to results):
- entry: the forecast's price at issue time, in the forecast's direction;
- stop: the far edge of the 80 % corridor (long: lower edge; short: upper edge). A correct corridor is crossed about
  one time in ten: reaching it means the idea was wrong;
- target: the near edge of the 50 % corridor in the trade's direction;
- time stop: if neither is hit, the trade closes at the horizon's end (where the Judge also checks the forecast);
- cost: judge.full_cost (spread, slippage, overnight financing for the nights held); a gap through the stop fills at the worse open price;
- inside one candle, if both stop and target were touched and the order is unknown, the stop counts (pessimistic).
The path between entry and exit is read from finer candles where they exist (e.g. 15-minute candles for a 1-hour
trade), otherwise from the horizon's own candles with the pessimistic rule.

Proof for a method, per metal and horizon: at least MIN_TRADES trades; average result per trade after cost above
zero with one-sided p below 0.05 divided by the number of methods tried (Bonferroni); overlapping multi-candle trades
count as n / k independent tests."""
from __future__ import annotations

import bisect
import math
import time

from . import candles, judge
from .db import DB
from .forecast import BASELINES, HORIZON_SPEC, METHODS

MIN_TRADES = 100
FINER = {"15m": "1m", "30m": "1m", "1h": "15m", "4h": "15m", "1d": "1h", "1w": "1d"}
P_MAX = 0.05


def _path(fine: tuple[list[int], list[dict]] | None, coarse: tuple[list[int], list[dict]], t0: int, t1: int,
          step_fine: int, step_coarse: int) -> tuple[list[dict], bool]:
    """Candles covering [t0, t1): the finer ones if they cover the whole window, else the coarse ones."""
    if fine:
        ts, rows = fine
        i, j = bisect.bisect_left(ts, t0), bisect.bisect_left(ts, t1)
        part = rows[i:j]
        if part and part[0]["t"] <= t0 + step_fine and part[-1]["t"] + step_fine >= t1 - step_fine:
            return part, True
    ts, rows = coarse
    i, j = bisect.bisect_left(ts, t0), bisect.bisect_left(ts, t1)
    return rows[i:j], False


def play(f: dict, path: list[dict], cost: float) -> dict | None:
    """One trade. f: price0, p_up, lo80, hi80, lo50, hi50, price1. Returns the result as a fraction of the entry."""
    if f["p_up"] == 0.5 or f["price1"] is None or not path:
        return None
    long = f["p_up"] > 0.5
    entry = f["price0"]
    stop = f["lo80"] if long else f["hi80"]
    target = f["hi50"] if long else f["lo50"]
    exit_px, how = None, "time"
    for c in path:
        hit_stop = c["l"] <= stop if long else c["h"] >= stop
        hit_target = c["h"] >= target if long else c["l"] <= target
        if hit_stop:      # first or together with the target: the stop counts (pessimistic)
            gap = c["o"] < stop if long else c["o"] > stop
            exit_px, how = (c["o"] if gap else stop), "stop"
            break
        if hit_target:
            exit_px, how = target, "target"
            break
    if exit_px is None:
        exit_px = f["price1"]
    ret = (exit_px / entry - 1) if long else (entry / exit_px - 1)
    return {"ret": ret - cost, "how": how, "long": long}


def _p_mean_above_zero(rs: list[float], k: int) -> float | None:
    n = len(rs)
    if n < 2:
        return None
    m = sum(rs) / n
    sd = math.sqrt(sum((r - m) ** 2 for r in rs) / (n - 1))
    if sd == 0:
        return 0.0 if m > 0 else 1.0
    z = m / (sd / math.sqrt(max(1.0, n / k)))
    return 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _summary(trades: list[dict], k: int) -> dict:
    rs = [t["ret"] for t in trades]
    n = len(rs)
    if not n:
        return {"n": 0}
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    eq = peak = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {"n": n, "win": len(wins) / n, "avg": sum(rs) / n, "total": sum(rs),
            "pf": (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else None, "max_dd": dd,
            "p": _p_mean_above_zero(rs, k),
            "stops": sum(t["how"] == "stop" for t in trades) / n, "targets": sum(t["how"] == "target" for t in trades) / n}


def simulate(db: DB, symbol: str, horizon: str, mode: str = "history") -> dict:
    """Every method's shadow trades on one metal and horizon, with the proof status and the session/mood split."""
    tf, k = HORIZON_SPEC[horizon]
    cost = judge.full_cost(symbol, horizon)
    step = candles.TF[tf]
    rows = [dict(r) for r in db.execute(
        "SELECT method, issued_t, target_t, price0, price1, p_up, lo50, hi50, lo80, hi80 FROM forecasts "
        "WHERE symbol=? AND horizon=? AND mode=? AND price1 IS NOT NULL AND p_up != 0.5 ORDER BY issued_t",
        (symbol, horizon, mode)).fetchall()]
    if not rows:
        return {"symbol": symbol, "horizon": horizon, "mode": mode, "methods": {}, "cost": cost}
    t0, t1 = rows[0]["issued_t"], max(r["target_t"] for r in rows)

    def load(t: str):
        cs = [dict(c) for c in db.execute("SELECT t, o, h, l, c FROM candles WHERE symbol=? AND tf=? AND t>=? AND t<? "
                                          "ORDER BY t", (symbol, t, t0 - candles.TF[t], t1)).fetchall()]
        return ([c["t"] for c in cs], cs)
    coarse = load(tf)
    fine_tf = FINER.get(tf)
    fine = load(fine_tf) if fine_tf else None
    by: dict[str, list[dict]] = {}
    finer_used = 0
    for f in rows:
        path, used = _path(fine, coarse, f["issued_t"], f["target_t"], candles.TF.get(fine_tf, step) if fine_tf
                           else step, step)
        res = play(f, path, cost)
        if res is None:
            continue
        finer_used += used
        h = (f["issued_t"] // 3600) % 24
        res["sess"] = "asia" if h >= 22 or h < 7 else "london" if h < 13 else "ny"
        res["t"] = f["issued_t"]
        by.setdefault(f["method"], []).append(res)
    tested = [m for m in by if m not in BASELINES and len(by[m]) >= MIN_TRADES]
    p_bar = P_MAX / max(1, len(tested))
    out = {}
    for m in METHODS:
        if m not in by:
            continue
        s = _summary(by[m], k)
        # Block 18, full report: risk-return per trade (mean / spread of results) and robustness — does the result
        # hold in BOTH halves of the period? One lucky stretch cannot make a method look steady.
        rs = [t["ret"] for t in by[m]]
        if len(rs) >= 2:
            mu = sum(rs) / len(rs)
            sd = math.sqrt(sum((r - mu) ** 2 for r in rs) / (len(rs) - 1))
            s["ratio"] = mu / sd if sd else None
            half = len(rs) // 2
            a, b = rs[:half], rs[half:]
            s["halves"] = [sum(a) / len(a) if a else None, sum(b) / len(b) if b else None]
            s["steady"] = bool(a and b and s["halves"][0] > 0 and s["halves"][1] > 0)
        s["status"] = ("bazis" if m in BASELINES else "az" if s["n"] < MIN_TRADES else
                       "sübut" if s["avg"] > 0 and s["p"] is not None and s["p"] < p_bar else "yox")
        groups = {}
        for g in ("asia", "london", "ny"):
            sub = [t for t in by[m] if t["sess"] == g]
            if sub:
                gs = _summary(sub, k)
                groups[g] = {key: gs.get(key) for key in ("n", "avg", "win", "p")}
        s["sessions"] = groups
        out[m] = s
    # «buy and hold» over the same windows, for comparison: the plain move per period, no stops, minus the cost
    bh = db.execute("SELECT AVG(price1 / price0 - 1) a, COUNT(*) n FROM forecasts WHERE symbol=? AND horizon=? "
                    "AND mode=? AND method='rw' AND price1 IS NOT NULL", (symbol, horizon, mode)).fetchone()
    return {"symbol": symbol, "horizon": horizon, "mode": mode, "methods": out, "cost": cost, "p_bar": p_bar,
            "buy_hold": {"avg": (bh["a"] - cost) if bh["a"] is not None else None, "n": bh["n"]},
            "finer_share": finer_used / max(1, sum(len(v) for v in by.values())), "computed": time.time()}


_CACHE: dict = {}


def cached(db: DB, symbol: str, horizon: str, mode: str = "history", ttl: float = 900) -> dict:
    key = (id(db), symbol, horizon, mode)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    out = simulate(db, symbol, horizon, mode)
    _CACHE[key] = (time.time(), out)
    return out
