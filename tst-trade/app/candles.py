"""Candles built from live ticks, and stored history. Times are UTC epoch seconds of the candle's start."""
from __future__ import annotations

from .db import DB

TF = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}
METALS = ("XAU", "XAG", "XPT", "XPD")
NAMES = {"XAU": "Qızıl", "XAG": "Gümüş", "XPT": "Platin", "XPD": "Palladium"}


def bucket(ts: float, tf: str) -> int:
    step = TF[tf]
    if tf == "1w":   # weeks start on Monday 00:00 UTC (epoch 0 was a Thursday)
        return int((ts - 345600) // step * step + 345600)
    return int(ts // step * step)


def add_tick(db: DB, symbol: str, ts: float, price: float) -> None:
    """Fold one price into every timeframe's current candle."""
    for tf in TF:
        t = bucket(ts, tf)
        db.execute(
            "INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'live') "
            "ON CONFLICT(symbol, tf, t) DO UPDATE SET h=max(h, excluded.h), l=min(l, excluded.l), c=excluded.c",
            (symbol, tf, t, price, price, price, price))


def store_history(db: DB, symbol: str, tf: str, rows: list[tuple[int, float, float, float, float]]) -> int:
    """History from a provider. A live candle already there is kept (it holds the newest prices)."""
    db.executemany(
        "INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'history') "
        "ON CONFLICT(symbol, tf, t) DO NOTHING",
        [(symbol, tf, int(t), o, h, l, c) for t, o, h, l, c in rows])
    return len(rows)


def get(db: DB, symbol: str, tf: str, limit: int = 300, before: int | None = None) -> list[dict]:
    sql = "SELECT t, o, h, l, c FROM candles WHERE symbol=? AND tf=?"
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
