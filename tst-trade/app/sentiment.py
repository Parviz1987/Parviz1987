"""Capital.com müştəri əhvalı (owner 28.11 00:20: «ikisini də et»; «nə qədər çox məlumat gətirsək, o qədər yaxşı» — and
every new voice is measured by the Judge before it may steer anything).

The broker publishes, per market, the share of its clients' open positions that are long. A crowd piled on one side is
often on the wrong side of the next move (a well-known contrarian idea for retail positioning) — but that is a claim,
so it is tested first. Read every 15 minutes with the live stream's OWN session (Capital.com blocks repeated logins, so
no login of its own); nothing is read while the stream has no session.

PRE-REGISTERED 28.11.2026 00:40 NY, before the first reading was stored (the rule cannot be fitted to the result):
  Reading   once a day: the first reading at or after 12:00 New York on a weekday (the crowd's position mid-session).
  Rule      contrarian on gold: long share above 50 % → gold DOWN over the next 24 hours; below 50 % → UP; 50 % → none.
  Trade     entry = open of the first 1-hour candle that starts after the reading; exit = close of the 1-hour candle
            that ends 24 hours after entry.
  Cost      judge.full_cost("XAU", "1d") (spread, slippage and one night).
  Proof     at least 60 readings; hits against 50 %, one-sided p < 0.05; the average after cost > 0; and both halves
            (first / second half by time) positive after cost. Fewer than 60: «az» — never «works».
  Gold decides; silver, platinum and palladium are shown only."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .db import DB

log = logging.getLogger("tst.sentiment")

NY = ZoneInfo("America/New_York")
EVERY = 900
HEALTH = "sent:health"
SCHEMA = "CREATE TABLE IF NOT EXISTS sentiment (symbol TEXT NOT NULL, ts INTEGER NOT NULL, long_pct REAL NOT NULL, " \
         "PRIMARY KEY (symbol, ts))"
REGISTERED = 1795844400          # 28.11.2026 00:40 NY: only readings after this count
MIN_N, P_BAR = 60, 0.05


def parse(data: object) -> dict[str, float]:
    """{"clientSentiments": [{"marketId": "GOLD", "longPositionPercentage": 63.0, ...}]} → {"XAU": 63.0, ...}"""
    from .providers.capital import SYMBOL
    rows = data.get("clientSentiments") if isinstance(data, dict) else None
    if rows is None and isinstance(data, dict) and "marketId" in data:
        rows = [data]
    out = {}
    for r in rows or []:
        sym = SYMBOL.get(str(r.get("marketId") or "").upper())
        try:
            v = float(r.get("longPositionPercentage"))
        except (TypeError, ValueError):
            continue
        if sym and 0 <= v <= 100:
            out[sym] = v
    return out


def health(db: DB, ok: bool | None, msg: str) -> None:
    db.put(HEALTH, json.dumps({"ok": ok, "msg": msg[:200], "ts": time.time()}, ensure_ascii=False))


async def fetch_once(db: DB, engine, now: float | None = None) -> str:
    now = time.time() if now is None else now
    db.script(SCHEMA)
    from .providers.capital import BASES, EPIC
    prov = engine.provider if engine is not None and engine.provider_name == "capital" else None
    tokens = getattr(prov, "tokens", None)
    if not tokens:
        health(db, None, "Capital.com axınının sessiyası hələ yoxdur (ayrıca giriş edilmir)")
        return "no session"
    base = BASES[getattr(prov, "env", None) or "real"]
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{base}/clientsentiment", params={"marketIds": ",".join(EPIC.values())},
                        headers={"CST": tokens["CST"], "X-SECURITY-TOKEN": tokens["X-SECURITY-TOKEN"]})
    if r.status_code != 200:
        health(db, False, f"Capital.com müştəri əhvalı: HTTP {r.status_code}")
        return f"HTTP {r.status_code}"
    got = parse(r.json())
    t = int(now // EVERY) * EVERY
    for sym, v in got.items():
        db.execute("INSERT OR REPLACE INTO sentiment(symbol, ts, long_pct) VALUES(?,?,?)", (sym, t, v))
    health(db, bool(got), "işləyir: " + ", ".join(f"{k} {v:.0f} % alışda" for k, v in sorted(got.items()))
           if got else "cavab boş gəldi")
    return "ok"


async def run(db: DB, engine) -> None:
    await asyncio.sleep(60)                     # let the stream log in first
    while True:
        try:
            await fetch_once(db, engine)
        except Exception as e:                  # a sentiment question must never take anything down
            health(db, False, f"{type(e).__name__}")
            log.warning("sentiment: %s", e)
        await asyncio.sleep(EVERY)


def latest(db: DB) -> dict:
    db.script(SCHEMA)
    out = {}
    for r in db.execute("SELECT symbol, ts, long_pct FROM sentiment s WHERE ts = (SELECT MAX(ts) FROM sentiment "
                        "WHERE symbol = s.symbol)").fetchall():
        day = db.execute("SELECT long_pct FROM sentiment WHERE symbol=? AND ts <= ? ORDER BY ts DESC LIMIT 1",
                         (r["symbol"], r["ts"] - 86400)).fetchone()
        out[r["symbol"]] = {"ts": r["ts"], "long_pct": r["long_pct"],
                            "change_24h": round(r["long_pct"] - day["long_pct"], 1) if day else None}
    return {"metals": out, "health": json.loads(db.get(HEALTH) or "null")}


def daily(db: DB, symbol: str = "XAU", since: float = REGISTERED) -> list[tuple[int, float]]:
    """The one reading per weekday: the first at or after 12:00 New York."""
    db.script(SCHEMA)
    seen, out = set(), []
    for r in db.execute("SELECT ts, long_pct FROM sentiment WHERE symbol=? AND ts > ? ORDER BY ts", (symbol, since)):
        d = datetime.fromtimestamp(r["ts"], NY)
        if d.weekday() >= 5 or d.hour < 12 or d.date() in seen:
            continue
        seen.add(d.date())
        out.append((r["ts"], r["long_pct"]))
    return out


def evaluate(db: DB, now: float | None = None) -> dict:
    """The pre-registered test (gold)."""
    from . import judge
    now = time.time() if now is None else now
    cost = judge.full_cost("XAU", "1d")
    rows = []
    for ts, pct in daily(db):
        if pct == 50:
            continue
        way = -1 if pct > 50 else 1
        a = db.execute("SELECT t, o FROM candles WHERE symbol='XAU' AND tf='1h' AND t >= ? ORDER BY t LIMIT 1",
                       (ts,)).fetchone()
        if not a or a["t"] + 86400 > now:
            continue
        b = db.execute("SELECT c FROM candles WHERE symbol='XAU' AND tf='1h' AND t = ?", (a["t"] + 86400 - 3600,)).fetchone()
        if not b or not a["o"]:
            continue
        rows.append((ts, (b["c"] / a["o"] - 1) * way))
    n = len(rows)
    hits = sum(1 for _, r in rows if r > 0)
    net = [r - cost for _, r in rows]
    half = n // 2
    halves = [sum(net[:half]) / half if half else None, sum(net[half:]) / (n - half) if n - half else None]
    if n < MIN_N:
        status, p = "az", None
    else:
        p = judge._p_one_sided(hits, n, 0.5)
        status = "sübut" if p < P_BAR and sum(net) > 0 and all(h is not None and h > 0 for h in halves) else "yox"
    return {"n": n, "need": MIN_N, "hit_rate": round(hits / n, 3) if n else None,
            "net_avg_pct": round(sum(net) / n * 100, 4) if n else None, "p": p, "status": status,
            "halves_net_pct": [round(h * 100, 4) if h is not None else None for h in halves]}
