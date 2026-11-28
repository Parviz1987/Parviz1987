"""Böyük oyunçu sübutu — keçmiş məlumatla (owner 27.11 23:10: «əvvəl sübut olsun, sonra edərik»). Databento's live
right was refused («A live data license is required»); the $125 credit buys history. Before paying $199 a month for the
live feed, the same rule the live feed would use is measured on past trades.

PRE-REGISTERED 27.11.2026 23:15 NY, before any trade history was downloaded (the rule cannot be fitted to the result):

  Data      GLBX.MDP3 trades of gold futures, the most traded contract (GC.v.0), the window the owner approves.
  Big trade a single trade of at least max(20 lots, the 99.9th percentile of the previous 5 000 trade sizes) — the same
            line as the live feed (orderflow.Flow); an ALARM is a trade at least twice that line, at most one per
            15 minutes (also as live). Side = the side that started it (B buy, A sell); trades without a side skipped.
  Trade     entry = the last traded price at the first whole minute after the alarm (time to react); exit = the last
            traded price 15 minutes after entry; buy alarm → long, sell alarm → short.
  Cost      judge.full_cost("XAU") is taken off every trade.
  Proof     at least 100 alarms; hits (moved the alarm's way) against 50 %, one-sided p < 0.01; the average after cost
            > 0; and both halves of the window (first / second half by time) must have a positive average after cost.
            Anything less: no proof → the live licence is not bought.
  Shown, not decisive: the 60-minute result, the count of big trades per day.

This module now only asks Databento what the download would cost (metadata.get_cost: free, nothing is downloaded).
The download and the measurement come after the owner approves the amount."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from .db import DB

log = logging.getLogger("tst.dbhist")

HIST = "https://hist.databento.com/v0/"
DATASET = "GLBX.MDP3"
SYMBOL = "GC.v.0"
WINDOWS = {"1 ay": 30, "3 ay": 91, "6 ay": 182, "12 ay": 365}
QUOTE = "dbhist:quote"
MIN_ALARMS, P_BAR, HOLD_MIN = 100, 0.01, 15


async def quote(db: DB, keys, now: float | None = None) -> dict:
    """What would the trades of the last 1 / 3 / 6 / 12 months cost (USD, from the $125 credit)? Stored for diag."""
    now = time.time() if now is None else now
    key = ((keys.get("databento") if keys is not None else None) or {}).get("key")
    if not key:
        out = {"ts": now, "ok": False, "msg": "Databento açarı yoxdur"}
        db.put(QUOTE, json.dumps(out))
        return out
    end = (datetime.fromtimestamp(now, timezone.utc) - timedelta(days=2)).date()    # history is complete up to here
    costs, errors = {}, []
    async with httpx.AsyncClient(timeout=30) as c:
        for name, days in WINDOWS.items():
            params = {"dataset": DATASET, "symbols": SYMBOL, "stype_in": "continuous", "schema": "trades",
                      "start": (end - timedelta(days=days)).isoformat(), "end": end.isoformat()}
            try:
                r = await c.get(HIST + "metadata.get_cost", params=params, auth=(key, ""))
                if r.status_code == 200:
                    costs[name] = round(float(r.json()), 2)
                else:
                    errors.append(f"{name}: HTTP {r.status_code} {r.text[:120]}")
            except (httpx.HTTPError, ValueError) as e:
                errors.append(f"{name}: {type(e).__name__}")
    out = {"ts": now, "ok": bool(costs), "symbol": SYMBOL, "schema": "trades", "end": end.isoformat(),
           "cost_usd": costs, "errors": errors}
    db.put(QUOTE, json.dumps(out, ensure_ascii=False))
    return out


async def run(db: DB, keys) -> None:
    """Once after a start (and once a day): the price list for the owner's decision. Free."""
    while True:
        try:
            last = json.loads(db.get(QUOTE) or "null") or {}
            if not last.get("ok") or time.time() - float(last.get("ts") or 0) > 86400:
                await quote(db, keys)
        except Exception as e:      # a price question must never take anything down
            log.warning("dbhist quote: %s", e)
        await asyncio.sleep(3600)
