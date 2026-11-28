"""«Böyük oyunçular indi» for the Bazar axını page (owner 28.11: the big players' data we can get without the Databento
live licence). Only a short reading of each free source the system already collects — the newest value, how it moved,
and what that usually means; the full tables, the rules built on them and the Judge's record stay on the Fundamental
page (one place per fact). Plus the Capital.com client sentiment (app/sentiment.py)."""
from __future__ import annotations

import time

from .db import DB

OZ_PER_TONNE = 32150.7466


def _rows(db: DB, sql: str, args: tuple = ()) -> list:
    try:
        return db.execute(sql, args).fetchall()
    except Exception:            # a source that never ran has no table yet
        return []


def cot(db: DB) -> dict:
    """Managed money (the big funds) per metal: net long, the week's change, where it stands in its last 3 years."""
    out = {}
    for sym in ("XAU", "XAG", "XPT", "XPD"):
        rows = _rows(db, "SELECT d, oi, mm_long, mm_short FROM cot WHERE symbol=? ORDER BY d DESC LIMIT 157", (sym,))
        if not rows or rows[0]["mm_long"] is None:
            continue
        nets = [r["mm_long"] - r["mm_short"] for r in rows if r["mm_long"] is not None and r["mm_short"] is not None]
        now = nets[0]
        rank = sum(1 for x in nets if x <= now) / len(nets) if len(nets) > 10 else None
        out[sym] = {"d": rows[0]["d"], "net": round(now), "change": round(now - nets[1]) if len(nets) > 1 else None,
                    "pct_of_oi": round(now / rows[0]["oi"] * 100, 1) if rows[0]["oi"] else None,
                    "rank_3y": round(rank, 2) if rank is not None else None}
    return out


def gld(db: DB) -> dict | None:
    rows = _rows(db, "SELECT d, tonnes FROM etf_gold WHERE fund='GLD' ORDER BY d DESC LIMIT 21")
    if not rows:
        return None
    t = [r["tonnes"] for r in rows]
    ch = lambda k: round(t[0] - t[k], 1) if len(t) > k else None
    return {"d": rows[0]["d"], "tonnes": round(t[0], 1), "ch_1d": ch(1), "ch_5d": ch(5), "ch_20d": ch(20)}


def central_banks(db: DB) -> list[dict]:
    """Net purchases per month (tonnes) of the reporting central banks, counting only banks reported in both months."""
    by: dict[str, dict[str, float]] = {}
    for r in _rows(db, "SELECT country, period, oz FROM cb_gold"):
        by.setdefault(r["period"], {})[r["country"]] = r["oz"]
    months = sorted(by)
    out = []
    for a, b in zip(months, months[1:]):
        both = set(by[a]) & set(by[b])
        if len(both) < 5:
            continue
        out.append({"month": b, "tonnes": round(sum(by[b][c] - by[a][c] for c in both) / OZ_PER_TONNE, 1),
                    "banks": len(both)})
    return out[-3:]


def india(db: DB) -> list[dict]:
    return [{"month": r["month"], "net_crore": round(r["net"])}
            for r in reversed(_rows(db, "SELECT month, net FROM india_etf ORDER BY month DESC LIMIT 3"))]


def shanghai(db: DB) -> dict | None:
    rows = _rows(db, "SELECT d, close, volume_kg FROM sge_gold ORDER BY d DESC LIMIT 21")
    if not rows or rows[0]["volume_kg"] is None:
        return None
    vols = [r["volume_kg"] for r in rows[1:] if r["volume_kg"]]
    avg = sum(vols) / len(vols) if vols else None
    return {"d": rows[0]["d"], "volume_kg": round(rows[0]["volume_kg"]),
            "vs_20d": round(rows[0]["volume_kg"] / avg, 2) if avg else None}


def summary(db: DB) -> dict:
    from . import sentiment
    return {"ts": time.time(), "cot": cot(db), "gld": gld(db), "central_banks": central_banks(db), "india": india(db),
            "shanghai": shanghai(db), "sentiment": sentiment.latest(db), "sentiment_test": sentiment.evaluate(db)}
