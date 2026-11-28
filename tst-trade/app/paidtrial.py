"""The one-month trial of the two paid sources (plan 27.11 step 11.1; owner bought both 27.11: FinancialJuice Developer
$99/month, renews 27.12; Databento Standard). Registered BEFORE the first live headline / trade was measured, so the rule
cannot be fitted to the result. Decision day: 22.12.2026 (NY) — five days before FinancialJuice renews, so the owner
can cancel what did not pay.

Two tests, each one direction, after the full cost of a real trade (judge.full_cost), against the bar 0.05 / 2 (two
tests), at least MIN_N cases; fewer cases → «az» (not enough to say), never «works»:

T1  FinancialJuice headline → gold, 15 minutes. A FinancialJuice headline the Reader labelled up/down for gold
    (strength ≥ 2). The trade can start only after the label exists: entry = open of the first 1-minute candle that
    starts at or after the label time; exit = close 15 minutes later. Hit = the move went the labelled way.
T2  Databento big trade → gold, 15 minutes. A «whale» alarm on gold futures (a single trade at least twice the usual
    big trade; one per 15 minutes). Buy → up, sell → down. Entry = open of the first 1-minute candle after the alarm;
    exit = close 15 minutes later.

Also shown, not a test: FinancialJuice speed (median seconds from the provider's publish time to arrival here) and how
many headlines arrived — over the last 7 days only (headlines are kept 7 days; the labels the test uses are kept); the number of whale alarms and big trades per metal."""
from __future__ import annotations

import re
import time

from . import judge
from .db import DB

REGISTERED = 1795831200          # 27.11.2026 21:00 NY (28.11 02:00 UTC): only cases after this count
DECIDE = 1797915600              # 22.12.2026 00:00 NY: the owner's decision day
P_BAR = 0.05 / 2
MIN_N = 30
HOLD_MIN = 15


def _table(db: DB, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _move(db: DB, t0: float, way: int) -> float | None:
    """Signed return of gold from the first 1-minute candle at or after t0 to 15 minutes later (None: no price)."""
    start = int(-(-t0 // 60) * 60)                                          # the next whole minute (or t0 itself)
    a = db.execute("SELECT o FROM candles WHERE symbol='XAU' AND tf='1m' AND t >= ? AND t < ? ORDER BY t LIMIT 1",
                   (start, start + 180)).fetchone()
    b = db.execute("SELECT c FROM candles WHERE symbol='XAU' AND tf='1m' AND t = ?",
                   (start + (HOLD_MIN - 1) * 60,)).fetchone()
    if not a or not b or not a["o"]:
        return None
    return (b["c"] / a["o"] - 1) * way


def _verdict(moves: list[float]) -> dict:
    n = len(moves)
    hits = sum(1 for m in moves if m > 0)
    cost = judge.full_cost("XAU")
    net = sum(m - cost for m in moves) / n if n else None
    if n < MIN_N:
        status, p = "az", None
    else:
        p = judge._p_one_sided(hits, n, 0.5)
        status = "sübut" if p < P_BAR and net is not None and net > 0 else "yox"
    return {"n": n, "need": MIN_N, "hit_rate": round(hits / n, 3) if n else None,
            "net_avg_pct": round(net * 100, 4) if net is not None else None, "p": p, "bar": P_BAR, "status": status}


def evaluate(db: DB, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    end = min(now - HOLD_MIN * 60, DECIDE)
    out: dict = {"registered": REGISTERED, "decide": DECIDE, "hold_min": HOLD_MIN}
    t1: list[float] = []
    speed: list[float] = []
    if _table(db, "news"):
        if _table(db, "news_ai"):
            for r in db.execute("SELECT a.ts, a.direction, a.metals FROM news_ai a WHERE a.uid LIKE 'fj:%' "
                                "AND a.direction IN ('up','down') AND a.strength >= 2 AND a.ts > ? AND a.ts < ?",
                                (REGISTERED, end)).fetchall():
                if "XAU" not in re.split(r"[,\s]+", r["metals"] or ""):
                    continue
                m = _move(db, r["ts"], 1 if r["direction"] == "up" else -1)
                if m is not None:
                    t1.append(m)
        speed = sorted(r[0] for r in db.execute(
            "SELECT received_ts - ts FROM news WHERE source='FinancialJuice' AND received_ts > ? AND received_ts IS NOT NULL",
            (REGISTERED,)).fetchall())
    out["T1_financialjuice"] = {**_verdict(t1), "headlines_7d": len(speed),
                                "median_delay_s_7d": round(speed[len(speed) // 2], 1) if speed else None}
    t2: list[float] = []
    alarms = 0
    if _table(db, "signals"):
        for r in db.execute("SELECT ts, text FROM signals WHERE kind='whale' AND metal='XAU' AND ts > ? AND ts < ?",
                            (REGISTERED, end)).fetchall():
            alarms += 1
            m = _move(db, r["ts"], 1 if "ALIŞ" in (r["text"] or "") else -1)
            if m is not None:
                t2.append(m)
    big = {}
    if _table(db, "flow_big"):
        big = {r["symbol"]: r["n"] for r in db.execute(
            "SELECT symbol, COUNT(*) n FROM flow_big WHERE ts > ? GROUP BY symbol", (REGISTERED,)).fetchall()}
    out["T2_databento"] = {**_verdict(t2), "alarms": alarms, "big_trades": big}
    return out
