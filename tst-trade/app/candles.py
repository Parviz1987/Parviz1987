"""Candles built from live ticks, and stored history. Times are UTC epoch seconds of the candle's start."""
from __future__ import annotations

from .db import DB

TF = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}
METALS = ("XAU", "XAG", "XPT", "XPD")
NAMES = {"XAU": "Qızıl", "XAG": "Gümüş", "XPT": "Platin", "XPD": "Palladium"}


SESSION_SHIFT = 7200   # the metals' trading day ends at 22:00 UTC (17:00 New York): Sunday-evening trading is Monday's


def bucket(ts: float, tf: str) -> int:
    """Start of the candle that holds ts. Daily and weekly candles follow the trading session: a tick at 22:00-24:00
    UTC belongs to the next day's candle (labelled at 00:00 UTC of that day), so Sunday evening is no stub day."""
    step = TF[tf]
    if tf == "1w":   # weeks start on Monday 00:00 UTC (epoch 0 was a Thursday)
        return int((ts + SESSION_SHIFT - 345600) // step * step + 345600)
    if tf == "1d":
        return int((ts + SESSION_SHIFT) // step * step)
    return int(ts // step * step)


def add_tick(db: DB, symbol: str, ts: float, price: float) -> None:
    """Fold one price into every timeframe's current candle. v = tick volume: how many times the price changed (a
    candle that began as history and is finished live keeps v NULL, so a part-counted candle is never used)."""
    for tf in TF:
        t = bucket(ts, tf)
        db.execute(
            "INSERT INTO candles(symbol, tf, t, o, h, l, c, origin, v) VALUES(?,?,?,?,?,?,?,'live',1) "
            "ON CONFLICT(symbol, tf, t) DO UPDATE SET h=max(h, excluded.h), l=min(l, excluded.l), c=excluded.c, "
            "v=CASE WHEN candles.v IS NULL THEN NULL WHEN candles.c != excluded.c THEN candles.v + 1 ELSE candles.v END",
            (symbol, tf, t, price, price, price, price))


def store_history(db: DB, symbol: str, tf: str, rows: list[tuple[int, float, float, float, float]],
                  replace: bool = False) -> int:
    """History from a provider. A live candle already there is kept (it holds the newest prices).
    replace=True: this source is the main one (the live feed's own broker) and overwrites older history rows."""
    if tf == "1d":   # no trading day on Saturday or Sunday: a source's weekend bar is not a candle here
        rows = [r for r in rows if (int(r[0]) // 86400 + 3) % 7 < 5]   # epoch day 0 was a Thursday (3)
    conflict = ("DO UPDATE SET o=excluded.o, h=excluded.h, l=excluded.l, c=excluded.c WHERE candles.origin='history'"
                if replace else "DO NOTHING")
    db.executemany(
        "INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'history') "
        f"ON CONFLICT(symbol, tf, t) {conflict}",
        [(symbol, tf, int(t), o, h, l, c) for t, o, h, l, c in rows])
    return len(rows)


def get(db: DB, symbol: str, tf: str, limit: int = 300, before: int | None = None) -> list[dict]:
    sql = "SELECT t, o, h, l, c, v FROM candles WHERE symbol=? AND tf=?"
    args: list = [symbol, tf]
    if before is not None:
        sql += " AND t<?"
        args.append(before)
    sql += " ORDER BY t DESC LIMIT ?"
    args.append(limit)
    rows = [dict(r) for r in db.execute(sql, args).fetchall()]
    rows.reverse()
    return rows


def closed(db: DB, symbol: str, tf: str, now: float, limit: int = 400) -> list[dict]:
    """Only finished candles (the current one is still moving)."""
    return get(db, symbol, tf, limit, before=bucket(now, tf))
