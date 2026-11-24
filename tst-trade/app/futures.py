"""Mərhələ 2 (Block 20): COMEX futures history from Databento, for the tests the broker's data cannot answer.

Why: Capital.com's CFD prices carry no real volume and a wide spread on platinum and palladium. The exchange's own
futures (GC gold, SI silver, PL platinum, PA palladium; continuous «most traded» contract) have real volume and a
spread of about one tick. With years of one-minute bars the owner's impulse idea and the «after the news» move can be
tested on thousands of cases instead of waiting weeks.

Money rule: nothing is bought without the owner. quote() asks Databento what the plan would cost (free metadata call)
and shows it; download() runs only after the owner presses the button with that quote in front of them, and refuses if
the cost is above the owner-approved limit. Data is stored in fut_candles (its own table: futures are not the CFD
prices the forecasts use)."""
from __future__ import annotations

import csv
import io
import json
import time
from datetime import datetime, timedelta, timezone

import httpx

from .db import DB

BASE = "https://hist.databento.com/v0"
DATASET = "GLBX.MDP3"
# metal -> continuous most-traded contract (volume roll)
SYMBOLS = {"XAU": "GC.v.0", "XAG": "SI.v.0", "XPT": "PL.v.0", "XPD": "PA.v.0"}
TICK = {"XAU": 0.10, "XAG": 0.005, "XPT": 0.10, "XPD": 0.50}      # one tick = about the futures spread
YEARS = 2
SCHEMA = """
CREATE TABLE IF NOT EXISTS fut_candles (symbol TEXT NOT NULL, t INTEGER NOT NULL, o REAL, h REAL, l REAL, c REAL,
  v REAL, PRIMARY KEY (symbol, t));
"""


def ensure(db: DB) -> None:
    db.script(SCHEMA)


def _window(now: float) -> tuple[str, str]:
    # history requests must end a little before «now» (the latest data is not historical yet)
    end = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    start = end - timedelta(days=365 * YEARS)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _params(sym: str, schema: str, now: float) -> dict:
    start, end = _window(now)
    return {"dataset": DATASET, "symbols": SYMBOLS[sym], "stype_in": "continuous", "schema": schema,
            "start": start, "end": end}


async def quote(key: str, now: float | None = None) -> dict:
    """What the plan (2 years of one-minute bars for 4 metals) would cost. Costs nothing to ask."""
    now = time.time() if now is None else now
    out = {"plan": f"{YEARS} il, dəqiqəlik şamlar (ohlcv-1m), {', '.join(SYMBOLS.values())}", "items": {}, "ts": now}
    total = 0.0
    async with httpx.AsyncClient(timeout=30.0) as c:
        for sym in SYMBOLS:
            r = await c.get(f"{BASE}/metadata.get_cost", params=_params(sym, "ohlcv-1m", now), auth=(key, ""))
            if r.status_code != 200:
                out["items"][sym] = {"error": f"HTTP {r.status_code}: {r.text[:160]}"}
                continue
            cost = float(r.json())
            out["items"][sym] = {"usd": round(cost, 2)}
            total += cost
    out["total_usd"] = round(total, 2)
    return out


def parse_ohlcv_csv(text: str) -> list[tuple]:
    """Databento CSV with pretty prices and times -> (t, o, h, l, c, v)."""
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            ts = r.get("ts_event", "")
            t = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()) if not ts.isdigit() else int(ts) // 10**9
            rows.append((t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"])))
        except (KeyError, ValueError):
            continue
    return rows


async def download(db: DB, key: str, limit_usd: float, report=None, now: float | None = None) -> dict:
    """Owner-approved only: check the price again, refuse above the limit, then load and store the bars."""
    ensure(db)
    q = await quote(key, now)
    if any("error" in v for v in q["items"].values()):
        return {"ok": False, "msg": "qiymət alınmadı: " + json.dumps(q["items"], ensure_ascii=False)[:300]}
    if q["total_usd"] > limit_usd:
        return {"ok": False, "msg": f"qiymət {q['total_usd']} $ təsdiq olunan {limit_usd} $-dan çoxdur: alınmadı"}
    got = {}
    async with httpx.AsyncClient(timeout=600.0) as c:
        for i, sym in enumerate(SYMBOLS):
            if report:
                report("history", "working", "W5 Fyuçers", i / len(SYMBOLS), f"Databento {SYMBOLS[sym]}")
            p = {**_params(sym, "ohlcv-1m", now or time.time()), "encoding": "csv", "pretty_px": "true",
                 "pretty_ts": "true", "map_symbols": "true", "compression": "none"}
            r = await c.get(f"{BASE}/timeseries.get_range", params=p, auth=(key, ""))
            if r.status_code != 200:
                got[sym] = f"xəta HTTP {r.status_code}: {r.text[:120]}"
                continue
            rows = parse_ohlcv_csv(r.text)
            db.executemany("INSERT OR REPLACE INTO fut_candles(symbol, t, o, h, l, c, v) VALUES(?,?,?,?,?,?,?)",
                           [(sym, *x) for x in rows])
            got[sym] = f"{len(rows)} şam"
    res = {"ok": True, "ts": time.time(), "cost_usd": q["total_usd"], "loaded": got}
    db.put("futures:last", json.dumps(res, ensure_ascii=False))
    if report:
        report("history", "done", note="Databento fyuçers: " + ", ".join(f"{k} {v}" for k, v in got.items()))
    return res
