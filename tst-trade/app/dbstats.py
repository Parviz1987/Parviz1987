"""CME həcm və açıq mövqelər (owner 28.11 «hə, başla»): CME's own daily statistics for every gold, silver, platinum and
palladium futures contract — open interest (how many contracts stay open: money coming in or leaving), cleared volume
and the settlement price — through Databento (licensed CME data, the owner's key, the usage-based credit). The CME
site itself blocks automated reading, so this is the permitted way.

Step 1 (this file now): only the price question (metadata.get_cost — free, nothing is downloaded) for one day (the
daily running cost), one year and five years (for a test on history). Nothing is bought before the owner approves the
amount."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from .db import DB

log = logging.getLogger("tst.dbstats")

HIST = "https://hist.databento.com/v0/"
DATASET = "GLBX.MDP3"
SYMBOLS = "GC.FUT,SI.FUT,PL.FUT,PA.FUT"          # every futures contract of each metal (parent symbology)
WINDOWS = {"1 gün": 1, "1 il": 365, "5 il": 1826}
QUOTE = "dbstats:quote"


async def quote(db: DB, keys, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    key = ((keys.get("databento") if keys is not None else None) or {}).get("key")
    if not key:
        out = {"ts": now, "ok": False, "msg": "Databento açarı yoxdur"}
        db.put(QUOTE, json.dumps(out, ensure_ascii=False))
        return out
    end = (datetime.fromtimestamp(now, timezone.utc) - timedelta(days=2)).date()
    costs, errors = {}, []
    async with httpx.AsyncClient(timeout=30) as c:
        for name, days in WINDOWS.items():
            params = {"dataset": DATASET, "symbols": SYMBOLS, "stype_in": "parent", "schema": "statistics",
                      "start": (end - timedelta(days=days)).isoformat(), "end": end.isoformat()}
            try:
                r = await c.get(HIST + "metadata.get_cost", params=params, auth=(key, ""))
                if r.status_code == 200:
                    costs[name] = round(float(r.json()), 4)
                else:
                    errors.append(f"{name}: HTTP {r.status_code} {r.text[:160]}")
            except (httpx.HTTPError, ValueError) as e:
                errors.append(f"{name}: {type(e).__name__}")
    out = {"ts": now, "ok": bool(costs), "symbols": SYMBOLS, "schema": "statistics", "end": end.isoformat(),
           "cost_usd": costs, "errors": errors}
    db.put(QUOTE, json.dumps(out, ensure_ascii=False))
    return out


async def run(db: DB, keys) -> None:
    await asyncio.sleep(45)
    while True:
        try:
            last = json.loads(db.get(QUOTE) or "null") or {}
            if not last.get("ok") or time.time() - float(last.get("ts") or 0) > 86400:
                await quote(db, keys)
        except Exception as e:      # a price question must never take anything down
            log.warning("dbstats quote: %s", e)
        await asyncio.sleep(3600)
