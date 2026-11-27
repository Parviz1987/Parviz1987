"""Who is right, day by day (owner 2026-11-27: «gün ərzində kim düz deyir, 15 dəqiqəlikdə, 1 saatlıqda, 1 gündə,
həftəlikdə — müqayisə edək»).

For a period (today, yesterday, the last 7 or 30 days, New York days) and a metal (or all four): every method's live
forecasts that were CHECKED in the period and took a side (the Judge's own rule: p_up exactly 0.5 is no side), how
many came true, and the chance of being right by luck in that same period: each up call is worth the market's up
share of that horizon in the period, each down call its down share. Being right more often than that chance, over
many calls, is what matters; the Judge decides proof (cost, multiple tests), this table only shows who leads.
Read only, from the forecasts table (its recent-forecasts index)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .db import DB

NY = ZoneInfo("America/New_York")
HORIZONS = ("15m", "1h", "4h", "1d", "1w")
PERIODS = ("day", "yesterday", "7d", "30d")
METALS = ("XAU", "XAG", "XPT", "XPD")


def window(period: str, now: float) -> tuple[float, float]:
    """[start, end) of the period in seconds; days are New York days."""
    midnight = datetime.fromtimestamp(now, NY).replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        return midnight.timestamp(), now
    if period == "yesterday":
        return (midnight - timedelta(days=1)).timestamp(), midnight.timestamp()
    days = 30 if period == "30d" else 7
    return now - days * 86400, now


def board(db: DB, symbol: str = "ALL", period: str = "day", now: float | None = None) -> dict:
    now = time.time() if now is None else now
    if period not in PERIODS:
        period = "day"
    start, end = window(period, now)
    syms = METALS if symbol == "ALL" else (symbol,)
    marks = ",".join("?" * len(HORIZONS))
    rows = []
    for s in syms:
        rows += db.execute(f"SELECT symbol, horizon, method, target_t, p_up, outcome, hit FROM forecasts WHERE symbol=? "
                           f"AND mode='live' AND target_t>=? AND target_t<? AND scored_ts IS NOT NULL "
                           f"AND horizon IN ({marks})", (s, int(start), int(end), *HORIZONS)).fetchall()
    # the market's own lean per horizon in the period: each checked moment once (all methods share it)
    seen, ups = set(), {}
    for r in rows:
        k = (r["symbol"], r["horizon"], r["target_t"])
        if r["outcome"] is None or k in seen:
            continue
        seen.add(k)
        u = ups.setdefault(r["horizon"], [0, 0])
        u[0] += r["outcome"]
        u[1] += 1
    market_up = {h: u[0] / u[1] for h, u in ups.items() if u[1]}
    methods: dict = {}
    for r in rows:
        if r["hit"] is None or r["outcome"] is None:
            continue
        up_share = market_up.get(r["horizon"], 0.5)
        c = methods.setdefault(r["method"], {}).setdefault(r["horizon"], {"n": 0, "right": 0, "up": 0, "chance": 0.0})
        c["n"] += 1
        c["right"] += r["hit"]
        said_up = r["p_up"] > 0.5
        c["up"] += int(said_up)
        c["chance"] += up_share if said_up else 1 - up_share
    for per in methods.values():
        for c in per.values():
            c["chance"] = c["chance"] / c["n"]
    return {"symbol": symbol, "period": period, "from": start, "to": end, "horizons": list(HORIZONS),
            "market_up": market_up, "methods": methods}
