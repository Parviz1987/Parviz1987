"""Koridor mühərriki v2 (owner 28.11: «hər ikisi olmalıdır — fiziki qızıl və fyuçers; birinci koridoru düzəlt»; plan
docs/PLAN-KORIDOR.md, stage 1). Direction is not forecastable here (eight labs, the corridor-edge labs, the friend's
system and the literature agree); volatility is. This module builds the price corridor from volatility alone and tests
it walk-forward against the corridor the system has today.

PRE-REGISTERED 28.11.2026 15:37 NY, before any v2 result was computed (the rule cannot be fitted to the result):
  Volatility  daily Parkinson variance PV = ln(high/low)² / (4 ln 2) from the daily candles. HAR on logs: the target
              is ln(mean PV over the next k trading days); regressors ln PV of the last day, ln mean PV of the last 5
              and of the last 22 days, for gold ln((GVZ/100)²/252) from the trading day before the last (published the
              next day), and the number of scheduled US releases (CPI, payrolls, Fed decision) among the next k days
              (dates known in advance). Ordinary least squares on the last 1 000 days whose target was complete before
              the forecast; refitted every 21 days; at least 300 days before the first forecast.
  Corridor    z = ln(close(t+k)/close(t)) / √(k·σ̂²) for the last 750 forecasts already complete; the lower and the upper
              edge are separate empirical quantiles of z (10 % / 90 % for the 80 % corridor, 25 % / 75 % for the 50 %);
              each tail's level then adapts online (adaptive conformal, γ = 0.005): a miss below widens the lower edge,
              no misses narrow it. Edge = close(t) · exp(q · √(k·σ̂²)).
  Test        walk-forward over all daily history, horizons 1d, 3d, 1w (5 days), 10d, 1mo (21 days), each metal. Scored
              only where the system's own corridor (method «vahid», else «up») exists for the same moment. Every k-th
              forecast is used for the comparison (no overlap). Winkler score of the 80 % corridor: (hi − lo + 10 ·
              distance outside) / price.
  Proof       gold, 1d and 1w both: coverage of the 80 % corridor within 80 ± 2.5 %, of the 50 % within 50 ± 3 %;
              v2's mean Winkler score lower than the system's on the same moments with a one-sided Diebold–Mariano
              p < 0.01; misses not clustered (P(miss | miss before) / P(miss) ≤ 1.5). Then v2 becomes the system's
              corridor; otherwise the present one stays and the result is written down."""
from __future__ import annotations

import json
import math
import time
from bisect import bisect_left
from datetime import datetime, timezone

from .db import DB

HORIZONS = {"1d": 1, "3d": 3, "1w": 5, "10d": 10, "1mo": 21}
FIT_WINDOW, REFIT, WARMUP, Q_WINDOW, GAMMA = 1000, 21, 300, 750, 0.005
LEVELS = {"80": (0.10, 0.90), "50": (0.25, 0.75)}
EVENT_KINDS = ("CPI", "Employment Situation", "FOMC")
KEY = "corridor:eval"
LN2x4 = 4 * math.log(2)


def _day(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")


def bars(db: DB, sym: str) -> list[dict]:
    return [dict(r) for r in db.execute("SELECT t, o, h, l, c FROM candles WHERE symbol=? AND tf='1d' ORDER BY t",
                                        (sym,)).fetchall()]


def parkinson(h: float, l: float) -> float | None:
    if not h or not l or h < l or h / l > 1.25:          # a broken bar (0 or > 25 % range) carries no information
        return None
    return max((math.log(h / l)) ** 2 / LN2x4, 1e-9)


def _event_days(db: DB) -> set[str]:
    try:
        return {_day(r["t"]) for r in db.execute(
            "SELECT t FROM ev_lib WHERE kind IN (?, ?, ?)", EVENT_KINDS).fetchall()}
    except Exception:
        return set()


def _gvz(db: DB) -> tuple[list[str], list[float]]:
    try:
        rows = db.execute("SELECT d, v FROM macro WHERE series='GVZCLS' AND v > 0 ORDER BY d").fetchall()
    except Exception:
        rows = []
    return [r["d"] for r in rows], [r["v"] for r in rows]


def _solve(xtx: list[list[float]], xty: list[float]) -> list[float] | None:
    """Gaussian elimination with a tiny ridge (the system has 4–6 unknowns)."""
    n = len(xty)
    a = [row[:] + [xty[i]] for i, row in enumerate(xtx)]
    for i in range(n):
        a[i][i] += 1e-9
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-12:
            return None
        a[c], a[p] = a[p], a[c]
        for r in range(n):
            if r != c:
                f = a[r][c] / a[c][c]
                for k in range(c, n + 1):
                    a[r][k] -= f * a[c][k]
    return [a[i][n] / a[i][i] for i in range(n)]


def _quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    pos = min(max(q, 0.0), 1.0) * (len(s) - 1)
    lo = int(pos)
    return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * (pos - lo)


class Engine:
    """One metal, one horizon: walks forward over the daily bars, producing for every bar t the corridor for t+k."""

    def __init__(self, db: DB, sym: str, k: int, b: list[dict] | None = None):
        self.sym, self.k = sym, k
        self.b = b if b is not None else bars(db, sym)
        self.days = [_day(x["t"]) for x in self.b]
        self.ev = _event_days(db)
        self.gd, self.gv = _gvz(db) if sym == "XAU" else ([], [])
        pv = [parkinson(x["h"], x["l"]) for x in self.b]
        last = None
        for i, v in enumerate(pv):                    # a broken bar takes the day before's value
            pv[i] = v if v is not None else last
            last = pv[i]
        self.pv = pv
        self.cum = [0.0]
        for v in pv:
            self.cum.append(self.cum[-1] + (v or 0.0))

    def _mean(self, a: int, b: int) -> float | None:      # mean PV over bars a..b inclusive
        if a < 0 or b >= len(self.pv) or any(self.pv[j] is None for j in (a, b)):
            return None
        return (self.cum[b + 1] - self.cum[a]) / (b - a + 1)

    def _x(self, i: int) -> list[float] | None:
        d, w, m = self.pv[i], self._mean(i - 4, i), self._mean(i - 21, i)
        if not d or not w or not m:
            return None
        x = [1.0, math.log(d), math.log(w), math.log(m)]
        if self.gd:
            j = bisect_left(self.gd, self.days[i - 1] if i else self.days[i]) - 1     # GVZ of the day before
            if j < 0:
                return None
            x.append(math.log((self.gv[j] / 100.0) ** 2 / 252))
        ahead = self.days[i + 1:i + 1 + self.k]
        x.append(float(sum(1 for dd in ahead if dd in self.ev)))
        return x

    def _y(self, i: int) -> float | None:
        m = self._mean(i + 1, i + self.k)
        return math.log(m) if m else None

    def run(self) -> list[dict]:
        """Every bar from WARMUP on: the corridor for k bars ahead (only past-complete data used)."""
        n, k = len(self.b), self.k
        beta, fitted_at = None, -10 ** 9
        sig: dict[int, float] = {}
        zs: list[tuple[int, float]] = []                  # (forecast bar, z) — usable once bar + k ≤ now
        alpha = {name: {"lo": lv[0], "hi": 1 - lv[1]} for name, lv in LEVELS.items()}
        pending: list[dict] = []
        out = []
        for i in range(WARMUP, n):
            # outcomes that became complete at bar i: adaptive levels and the z pool
            done = [p for p in pending if p["i"] + k <= i]
            pending = [p for p in pending if p["i"] + k > i]
            for p in done:
                r = math.log(self.b[p["i"] + k]["c"] / self.b[p["i"]]["c"])
                zs.append((p["i"], r / math.sqrt(k * sig[p["i"]])))
                if p["edges"] is None:
                    continue                          # warm-up (no corridor yet): nothing to adapt
                for name, lv in LEVELS.items():
                    lo, hi = p["edges"][name]
                    miss_lo = 1.0 if self.b[p["i"] + k]["c"] < lo else 0.0
                    miss_hi = 1.0 if self.b[p["i"] + k]["c"] > hi else 0.0
                    a = alpha[name]
                    a["lo"] = min(0.45, max(0.003, a["lo"] + GAMMA * (lv[0] - miss_lo)))
                    a["hi"] = min(0.45, max(0.003, a["hi"] + GAMMA * ((1 - lv[1]) - miss_hi)))
            if i - fitted_at >= REFIT or beta is None:
                rows = [(self._x(j), self._y(j)) for j in range(max(22, i - k - FIT_WINDOW), i - k + 1)]
                rows = [(x, y) for x, y in rows if x and y is not None]
                if len(rows) >= 200:
                    p_ = len(rows[0][0])
                    xtx = [[sum(x[a] * x[b] for x, _ in rows) for b in range(p_)] for a in range(p_)]
                    xty = [sum(x[a] * y for x, y in rows) for a in range(p_)]
                    beta = _solve(xtx, xty) or beta
                    fitted_at = i
            x = self._x(i)
            if beta is None or x is None:
                continue
            s2 = math.exp(sum(bj * xj for bj, xj in zip(beta, x)))
            sig[i] = s2
            pool = [z for j, z in zs[-Q_WINDOW:]]
            if len(pool) < 100:
                pending.append({"i": i, "edges": None})
                continue
            scale = math.sqrt(k * s2)
            c = self.b[i]["c"]
            edges = {nm: (c * math.exp(_quantile(pool, alpha[nm]["lo"]) * scale),
                          c * math.exp(_quantile(pool, 1 - alpha[nm]["hi"]) * scale)) for nm in LEVELS}
            pending.append({"i": i, "edges": edges})
            out.append({"i": i, "t": self.b[i]["t"], "next_t": self.b[i + 1]["t"] if i + 1 < n else None,
                        "price": c, "lo50": edges["50"][0], "hi50": edges["50"][1],
                        "lo80": edges["80"][0], "hi80": edges["80"][1],
                        "price1": self.b[i + k]["c"] if i + k < n else None})
        return out


def _winkler(lo: float, hi: float, y: float, price: float) -> float:
    return ((hi - lo) + 10.0 * max(0.0, lo - y, y - hi)) / price


def evaluate(db: DB, sym: str = "XAU", horizon: str = "1d") -> dict:
    """v2 against the system's corridor on the same moments, every k-th one (no overlap)."""
    from . import judge
    k = HORIZONS[horizon]
    v2 = [r for r in Engine(db, sym, k).run() if r["price1"] is not None and r["next_t"]]
    sysrows = {}
    for r in db.execute("SELECT issued_t, price0, price1, lo50, hi50, lo80, hi80, method FROM forecasts WHERE "
                        "symbol=? AND horizon=? AND method IN ('vahid','up') AND price1 IS NOT NULL "
                        "ORDER BY issued_t, method DESC", (sym, horizon)).fetchall():
        sysrows.setdefault(r["issued_t"], dict(r))
    pairs = [(r, sysrows[r["next_t"]]) for r in v2 if r["next_t"] in sysrows]
    if horizon != "1w":
        pairs = pairs[::k]          # daily-issued horizons overlap: every k-th; weekly forecasts never overlap
    n = len(pairs)
    if n < 30:
        return {"symbol": sym, "horizon": horizon, "n": n, "status": "az"}
    # both corridors are scored on the system's own target price (its official outcome for that moment)
    in80 = [r["lo80"] <= s["price1"] <= r["hi80"] for r, s in pairs]
    in50 = [r["lo50"] <= s["price1"] <= r["hi50"] for r, s in pairs]
    w2 = [_winkler(r["lo80"], r["hi80"], s["price1"], r["price"]) for r, s in pairs]
    ws = [_winkler(s["lo80"], s["hi80"], s["price1"], s["price0"]) for _, s in pairs]
    d = [a - b for a, b in zip(w2, ws)]
    mean_d = sum(d) / n
    sd = math.sqrt(sum((x - mean_d) ** 2 for x in d) / (n - 1)) or 1e-12
    t = mean_d / (sd / math.sqrt(n))
    p = 0.5 * (1 + math.erf(t / math.sqrt(2)))              # one-sided: v2 lower (t < 0) is what counts
    miss = [not x for x in in80]
    pm = sum(miss) / n
    after = [miss[i] for i in range(1, n) if miss[i - 1]]
    cluster = (sum(after) / len(after)) / pm if after and pm else None
    c80, c50 = sum(in80) / n, sum(in50) / n
    ok = abs(c80 - 0.80) <= 0.025 and abs(c50 - 0.50) <= 0.03 and mean_d < 0 and p < 0.01 and \
        (cluster is None or cluster <= 1.5)
    sys_c80 = sum(s["lo80"] <= s["price1"] <= s["hi80"] for _, s in pairs) / n
    return {"symbol": sym, "horizon": horizon, "n": n, "first": _day(pairs[0][0]["t"]), "last": _day(pairs[-1][0]["t"]),
            "cover80": round(c80, 3), "cover50": round(c50, 3), "sys_cover80": round(sys_c80, 3),
            "width80_pct": round(sum((r["hi80"] - r["lo80"]) / r["price"] for r, _ in pairs) / n * 100, 3),
            "sys_width80_pct": round(sum((s["hi80"] - s["lo80"]) / s["price0"] for _, s in pairs) / n * 100, 3),
            "winkler_pct": round(sum(w2) / n * 100, 3), "sys_winkler_pct": round(sum(ws) / n * 100, 3),
            "dm_t": round(t, 2), "p": p, "cluster": round(cluster, 2) if cluster else None,
            "status": "sübut" if ok else "yox"}


def evaluate_all(db: DB) -> dict:
    out = {"ts": time.time(), "cells": {}}
    for sym in ("XAU", "XAG", "XPT", "XPD"):
        for h in HORIZONS:
            try:
                out["cells"][f"{sym}:{h}"] = evaluate(db, sym, h)
            except Exception as e:      # one cell's failure is shown, never hides the others
                out["cells"][f"{sym}:{h}"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    g1, gw = out["cells"].get("XAU:1d", {}), out["cells"].get("XAU:1w", {})
    out["decision"] = "v2 keçdi" if g1.get("status") == "sübut" and gw.get("status") == "sübut" else "v2 keçmədi"
    db.put(KEY, json.dumps(out, ensure_ascii=False))
    return out


async def run(db: DB) -> None:
    import asyncio
    import logging
    await asyncio.sleep(120)
    while True:
        try:
            await asyncio.to_thread(evaluate_all, db)
        except Exception as e:
            logging.getLogger("tst.corridor").warning("corridor eval: %s", e)
        await asyncio.sleep(86400)
