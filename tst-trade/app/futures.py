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
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=180.0)) as c:   # a 2-year price check can be slow
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


async def quote_saved(db: DB, key: str) -> dict:
    q = await quote(key)
    db.put("futures:quote", json.dumps(q, ensure_ascii=False))
    return q


def _months(start: str, end: str) -> list[tuple[str, str]]:
    out, d = [], datetime.fromisoformat(start)
    stop = datetime.fromisoformat(end)
    while d < stop:
        nxt = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
        out.append((d.strftime("%Y-%m-%d"), min(nxt, stop).strftime("%Y-%m-%d")))
        d = nxt
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
    try:
        q = await quote(key, now)
    except httpx.HTTPError as e:
        # the price check timed out: the quote the owner approved stands (the plan is the same and the limit holds)
        q = json.loads(db.get("futures:quote") or "null")
        if not q:
            return {"ok": False, "msg": f"qiymət yoxlanmadı: {type(e).__name__}"}
    if any("error" in v for v in q["items"].values()):
        return {"ok": False, "msg": "qiymət alınmadı: " + json.dumps(q["items"], ensure_ascii=False)[:300]}
    if q["total_usd"] > limit_usd:
        return {"ok": False, "msg": f"qiymət {q['total_usd']} $ təsdiq olunan {limit_usd} $-dan çoxdur: alınmadı"}
    # One month per request (a two-year request timed out on 2026-11-24): small answers, little memory, and a month
    # already stored is never asked (and paid) for again — a broken download resumes where it stopped.
    start, end = _window(now or time.time())
    months = _months(start, end)
    got: dict[str, int] = {}
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0)) as c:
        for i, sym in enumerate(SYMBOLS):
            got[sym] = 0
            for j, (a, b) in enumerate(months):
                ta = datetime.fromisoformat(a).replace(tzinfo=timezone.utc).timestamp()
                tb = datetime.fromisoformat(b).replace(tzinfo=timezone.utc).timestamp()
                if db.execute("SELECT 1 FROM fut_candles WHERE symbol=? AND t>=? AND t<? LIMIT 1",
                              (sym, ta, tb)).fetchone():
                    continue
                if report and j % 3 == 0:
                    report("history", "working", "W5 Fyuçers", (i + j / len(months)) / len(SYMBOLS),
                           f"Databento {SYMBOLS[sym]} {a[:7]}")
                p = {"dataset": DATASET, "symbols": SYMBOLS[sym], "stype_in": "continuous", "schema": "ohlcv-1m",
                     "start": a, "end": b, "encoding": "csv", "pretty_px": "true", "pretty_ts": "true",
                     "map_symbols": "true", "compression": "none"}
                try:
                    r = await c.get(f"{BASE}/timeseries.get_range", params=p, auth=(key, ""))
                except httpx.HTTPError as e:
                    errors.append(f"{sym} {a[:7]}: {type(e).__name__}")
                    continue
                if r.status_code != 200:
                    errors.append(f"{sym} {a[:7]}: HTTP {r.status_code} {r.text[:80]}")
                    continue
                import asyncio
                rows = await asyncio.to_thread(parse_ohlcv_csv, r.text)       # CPU and DB work off the event loop
                await asyncio.to_thread(db.executemany, "INSERT OR REPLACE INTO fut_candles(symbol, t, o, h, l, c, v) "
                                        "VALUES(?,?,?,?,?,?,?)", [(sym, *x) for x in rows])
                got[sym] += len(rows)
    total = {sym: db.execute("SELECT COUNT(*) n FROM fut_candles WHERE symbol=?", (sym,)).fetchone()["n"]
             for sym in SYMBOLS}
    res = {"ok": not errors, "ts": time.time(), "cost_usd": q["total_usd"], "loaded_now": got, "stored": total,
           "errors": errors[:12]}
    db.put("futures:last", json.dumps(res, ensure_ascii=False))
    if not errors:          # Block 21: the tests run once the data is complete (CPU work: off the event loop)
        import asyncio
        from . import futstudy
        if report:
            report("history", "working", "W6 Sınaqlar", 0.95, "fyuçers sınaqları hesablanır")
        try:
            await asyncio.to_thread(futstudy.run_and_store, db)
            res["study"] = "hesablandı"
        except Exception as e:
            res["study"] = f"xəta: {type(e).__name__}: {str(e)[:120]}"
        db.put("futures:last", json.dumps(res, ensure_ascii=False))
    if report:
        report("history", "done" if not errors else "error",
               note="Databento fyuçers: " + ", ".join(f"{k} {v} şam" for k, v in total.items()) +
                    (f"; {len(errors)} ay alınmadı" if errors else ""))
    return res


# ---------- daily top-up (owner 2026-11-25: «buna icazə verirəm» — about 0.35 $ a month, from the free credit) ----------
DAILY_CAP_USD = 1.0           # hard monthly ceiling for the daily top-up; above it nothing is bought that month


def daily_window(db: DB, sym: str, now: float, avail_end: datetime | None = None) -> tuple[str, str] | None:
    """From the minute after the newest stored bar to today 00:00 UTC, or to where Databento's history ends if that is
    earlier (asking past it is refused: «dataset_unavailable_range»). Whole hours; nothing twice."""
    last = db.execute("SELECT MAX(t) t FROM fut_candles WHERE symbol=?", (sym,)).fetchone()["t"]
    if last is None:
        return None
    start = datetime.fromtimestamp(last + 60, timezone.utc)
    end = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if avail_end is not None and avail_end < end:
        end = avail_end.replace(minute=0, second=0, microsecond=0)
    if start >= end:
        return None
    return start.strftime("%Y-%m-%dT%H:%M"), end.strftime("%Y-%m-%dT%H:%M")


async def daily_refresh(db: DB, key: str, now: float | None = None) -> dict:
    """Load the bars since the last stored one for the 4 metals, only if the owner approved the daily top-up and the
    month's spend stays under DAILY_CAP_USD (the price is asked first, free)."""
    ensure(db)
    now = time.time() if now is None else now
    if not json.loads(db.get("futures:daily_approved") or "null"):
        return {"ok": False, "msg": "gündəlik təzələmə təsdiqlənməyib"}
    month = time.strftime("%Y-%m", time.gmtime(now))
    spent = float(db.get(f"futures:daily_spent:{month}") or 0)
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=180.0)) as c:
        avail = None
        try:              # where the exchange's history ends right now (free); newer minutes are not historical yet
            r = await c.get(f"{BASE}/metadata.get_dataset_range", params={"dataset": DATASET}, auth=(key, ""))
            if r.status_code == 200:
                avail = datetime.fromisoformat(str(r.json().get("end", "")).replace("Z", "+00:00")[:25])
                if avail.tzinfo is None:
                    avail = avail.replace(tzinfo=timezone.utc)
        except (httpx.HTTPError, ValueError, AttributeError):
            avail = None
        wins = {s: daily_window(db, s, now, avail) for s in SYMBOLS}
        wins = {s: w for s, w in wins.items() if w and w[0] < w[1]}
        if not wins:
            return {"ok": True, "msg": "yeni məlumat yoxdur", "loaded": {}}
        cost = 0.0
        costs: dict[str, float] = {}
        for sym, (a, b) in wins.items():
            r = await c.get(f"{BASE}/metadata.get_cost", auth=(key, ""), params={
                "dataset": DATASET, "symbols": SYMBOLS[sym], "stype_in": "continuous", "schema": "ohlcv-1m",
                "start": a, "end": b})
            if r.status_code != 200:
                return {"ok": False, "msg": f"qiymət alınmadı: HTTP {r.status_code} {r.text[:120]}"}
            costs[sym] = float(r.json())
            cost += costs[sym]
        if spent + cost > DAILY_CAP_USD:
            return {"ok": False, "msg": f"aylıq hədd {DAILY_CAP_USD} $: bu ay {spent:.2f} $ + {cost:.2f} $ olardı — alınmadı"}
        loaded, errors = {}, []
        for sym, (a, b) in wins.items():
            p = {"dataset": DATASET, "symbols": SYMBOLS[sym], "stype_in": "continuous", "schema": "ohlcv-1m",
                 "start": a, "end": b, "encoding": "csv", "pretty_px": "true", "pretty_ts": "true",
                 "map_symbols": "true", "compression": "none"}
            try:
                r = await c.get(f"{BASE}/timeseries.get_range", params=p, auth=(key, ""))
            except httpx.HTTPError as e:
                errors.append(f"{sym}: {type(e).__name__}")
                continue
            if r.status_code != 200:
                errors.append(f"{sym}: HTTP {r.status_code} {r.text[:80]}")
                continue
            import asyncio
            rows = await asyncio.to_thread(parse_ohlcv_csv, r.text)
            await asyncio.to_thread(db.executemany, "INSERT OR REPLACE INTO fut_candles(symbol, t, o, h, l, c, v) "
                                    "VALUES(?,?,?,?,?,?,?)", [(sym, *x) for x in rows])
            loaded[sym] = len(rows)
    paid = sum(costs[s] for s in loaded)       # only data actually delivered is billed (a refused request costs 0)
    db.put(f"futures:daily_spent:{month}", f"{spent + paid:.4f}")
    res = {"ok": not errors, "ts": now, "cost_usd": round(paid, 4), "month_spent_usd": round(spent + paid, 4),
           "loaded": loaded, "errors": errors}
    db.put("futures:daily_last", json.dumps(res, ensure_ascii=False))
    return res
