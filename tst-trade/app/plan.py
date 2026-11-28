"""Alış-satış planı — fiziki qızıl və fyuçers (owner 28.11: «həm fiziki qızıl alıb satıram, həm fyuçers; ikisi də hazır
olsun»; docs/PLAN-KORIDOR.md stages 2 and 3). Built on the system's own corridor (calibrated: 1-day 80 % corridor held
80.3–80.5 % over eight years). The corridor does not tell the direction; it tells how far the price is likely to go —
that is what a buyer's limit price, a seller's limit price, a stop and a position size need.

PRE-REGISTERED 28.11.2026 15:48 NY, before any of these results was computed:
  Physical (stage 2) — a buyer who must buy within a window (1 trading day, or 1 week) leaves a limit order at the
  corridor's lower edge: P1 at the 50 % corridor's lower edge (25 % quantile), P2 at the 80 % one (10 %). It fills if
  the window's lowest price reaches it (one resting order: the order of the day's moves does not matter); if not, the
  buyer buys at the window's last close. A seller mirrors it at the upper edges (S1, S2). The saving is measured against
  buying (selling) at the window's last close — the same window, so gold's general rise in these years does not count as
  skill. A plan is «useful» when its mean saving > 0 with a one-sided t-test p < 0.01 over non-overlapping windows and
  both halves of the history are positive. Shown, not deciding: the fill rate, the worst 5 % of outcomes, the saving
  against acting at once.
  Futures (stage 3) — no direction (the Judge proves none today: «GÖZLƏ»). The corridor gives the stop and the size;
  measured from history and shown: how often the price TOUCHES each edge inside the window (a stop is hit by a touch, not
  by the close — so far more often than the corridor's 10 % / 25 %)."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone

from .db import DB

OZ = {"GC": 100, "MGC": 10}                       # COMEX gold contract sizes (troy ounces)
WINDOWS = {"1d": "1 gün", "1w": "1 həftə"}
KEY = "plan:eval"


def _day(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")


def _rows(db: DB, sym: str, horizon: str) -> list[dict]:
    """The system's corridor per forecast moment («vahid», else «up») with the window's daily low, high and close."""
    from .labs import _corridor_rows, _path
    out = []
    for r in _corridor_rows(db, sym, horizon):
        days = _path(db, sym, r["issued_t"], r["target_t"])
        if not days:
            continue
        out.append({"t": r["issued_t"], "price0": r["price0"], "close": days[-1]["c"],
                    "low": min(d["l"] for d in days), "high": max(d["h"] for d in days),
                    "lo50": r["lo50"], "hi50": r["hi50"], "lo80": r["lo80"], "hi80": r["hi80"]})
    return out


def _stats(savings: list[tuple[str, float]], filled: int) -> dict:
    n = len(savings)
    if n < 30:
        return {"n": n, "status": "az"}
    xs = [s for _, s in savings]
    mean = sum(xs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1)) or 1e-12
    t = mean / (sd / math.sqrt(n))
    p = 1 - 0.5 * (1 + math.erf(t / math.sqrt(2)))
    half = n // 2
    h1, h2 = sum(xs[:half]) / half, sum(xs[half:]) / (n - half)
    worst = sorted(xs)[max(0, int(0.05 * n) - 1)]
    ok = mean > 0 and p < 0.01 and h1 > 0 and h2 > 0
    return {"n": n, "first": savings[0][0], "last": savings[-1][0], "fill_rate": round(filled / n, 3),
            "mean_saving_pct": round(mean * 100, 4), "p": p, "halves_pct": [round(h1 * 100, 4), round(h2 * 100, 4)],
            "worst5_pct": round(worst * 100, 3), "status": "faydalı" if ok else "yox"}


def physical(db: DB, sym: str = "XAU", horizon: str = "1d") -> dict:
    rows = _rows(db, sym, horizon)
    out = {}
    for name, side, edge in (("P1", "buy", "lo50"), ("P2", "buy", "lo80"), ("S1", "sell", "hi50"), ("S2", "sell", "hi80")):
        sv, sv_now, filled = [], [], 0
        for r in rows:
            lim = r[edge]
            hit = r["low"] <= lim if side == "buy" else r["high"] >= lim
            px = lim if hit else r["close"]
            filled += hit
            if side == "buy":
                sv.append((_day(r["t"]), (r["close"] - px) / r["close"]))
                sv_now.append((r["price0"] - px) / r["price0"])
            else:
                sv.append((_day(r["t"]), (px - r["close"]) / r["close"]))
                sv_now.append((px - r["price0"]) / r["price0"])
        st = _stats(sv, filled)
        if sv_now:
            st["vs_now_pct"] = round(sum(sv_now) / len(sv_now) * 100, 4)
        out[name] = st
    return out


def touches(db: DB, sym: str = "XAU", horizon: str = "1d") -> dict:
    """How often the price touches each edge inside the window (what a stop or a limit order meets)."""
    rows = _rows(db, sym, horizon)
    n = len(rows)
    if n < 30:
        return {"n": n}
    f = lambda cond: round(sum(1 for r in rows if cond(r)) / n, 3)
    return {"n": n, "lo80": f(lambda r: r["low"] <= r["lo80"]), "hi80": f(lambda r: r["high"] >= r["hi80"]),
            "lo50": f(lambda r: r["low"] <= r["lo50"]), "hi50": f(lambda r: r["high"] >= r["hi50"]),
            "close_below_lo80": f(lambda r: r["close"] < r["lo80"]), "close_above_hi80": f(lambda r: r["close"] > r["hi80"])}


def evaluate(db: DB) -> dict:
    out = {"ts": time.time(), "physical": {}, "touches": {}}
    for sym in ("XAU", "XAG"):
        for h in WINDOWS:
            try:
                out["physical"][f"{sym}:{h}"] = physical(db, sym, h)
                out["touches"][f"{sym}:{h}"] = touches(db, sym, h)
            except Exception as e:
                out["physical"][f"{sym}:{h}"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    db.put(KEY, json.dumps(out, ensure_ascii=False))
    return out


def today(db: DB) -> dict:
    """The newest live corridor per metal and window: what to put in the order book now."""
    out = {}
    for sym in ("XAU", "XAG", "XPT", "XPD"):
        for h in WINDOWS:
            r = db.execute("SELECT issued_t, target_t, price0, lo50, hi50, lo80, hi80, method FROM forecasts WHERE "
                           "symbol=? AND horizon=? AND mode='live' AND method IN ('vahid','up') ORDER BY issued_t DESC, "
                           "method DESC LIMIT 1", (sym, h)).fetchone()
            if r:
                out[f"{sym}:{h}"] = {k: r[k] for k in ("issued_t", "target_t", "price0", "lo50", "hi50", "lo80", "hi80")}
    return out


def size(capital: float, risk_pct: float, entry: float, stop: float, contract: str = "MGC") -> dict:
    """Futures position size: the number of contracts whose loss at the stop is at most capital × risk %."""
    per = abs(entry - stop) * OZ.get(contract, 10)
    budget = capital * risk_pct / 100.0
    n = int(budget // per) if per > 0 else 0
    return {"contracts": n, "loss_at_stop": round(n * per, 2), "per_contract": round(per, 2), "budget": round(budget, 2)}


async def run(db: DB) -> None:
    import asyncio
    import logging
    await asyncio.sleep(150)
    while True:
        try:
            await asyncio.to_thread(evaluate, db)
        except Exception as e:
            logging.getLogger("tst.plan").warning("plan eval: %s", e)
        await asyncio.sleep(86400)
