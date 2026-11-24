"""İmpuls izləyicisi — araşdırma (owner's idea 2026-11-24): big players move the price within seconds; we see it a
minute later. Does the move go on after that minute, so that following it pays — or does it come back?

The study, from our own stored one-minute candles (last 30 days) and, where they exist, the raw price updates (last 3
days), with no look-ahead:
- the usual one-minute move is an exponential average of past absolute moves (only minutes BEFORE t);
- an impulse is a minute whose move is at least K times the usual (K = 4 and 6) and at least a floor;
- we act one minute later: entry at the close of minute t+1 (the minute we need to see it), exit H minutes after
  (5, 15, 30); «continues» = the exit is further in the impulse's direction than the entry;
- each result is net of the spread and slippage (judge.full_cost); impulses within 30 minutes of the previous one are skipped
  (one move, one test);
- where raw updates exist, impulses are split by activity: the minute's updates vs their usual count (big players
  trading -> many updates).
Read-only: nothing here forecasts or trades; it answers whether an «impulse» method is worth building."""
from __future__ import annotations

import math
import time

from .db import DB

KS = (4.0, 6.0)
HS = (5, 15, 30)
FLOOR = {"XAU": 0.0003, "XAG": 0.0006, "XPT": 0.0006, "XPD": 0.0008}
GAP = 30


def _p_two(hits: int, n: int) -> float | None:
    if n < 10:
        return None
    z = (hits - n / 2) / math.sqrt(n / 4)
    return round(1 - math.erf(abs(z) / math.sqrt(2)), 4)


def study(db: DB, now: float | None = None) -> dict:
    from .judge import full_cost
    now = time.time() if now is None else now
    out = {"computed": now, "metals": {}}
    for sym in ("XAU", "XAG", "XPT", "XPD"):
        rows = db.execute("SELECT t, c FROM candles WHERE symbol=? AND tf='1m' AND t > ? ORDER BY t",
                          (sym, now - 30 * 86400)).fetchall()
        if len(rows) < 2000:
            out["metals"][sym] = {"note": f"dəqiqəlik şam azdır ({len(rows)})"}
            continue
        ts = [r["t"] for r in rows]
        cs = [r["c"] for r in rows]
        idx = {t: i for i, t in enumerate(ts)}
        ticks = {}
        for r in db.execute("SELECT CAST(ts / 60 AS INTEGER) * 60 m, COUNT(*) n FROM ticks WHERE symbol=? AND ts > ? "
                            "GROUP BY m", (sym, now - 3 * 86400)).fetchall():
            ticks[r["m"]] = r["n"]
        ew, ew_tick = None, None
        last_imp = -10 ** 9
        res: dict[tuple, list] = {}
        for i in range(1, len(rows) - 1):
            if ts[i] - ts[i - 1] != 60 or not cs[i - 1]:
                continue
            r = cs[i] / cs[i - 1] - 1
            a = abs(r)
            usual = ew
            ew = a if ew is None else ew + (a - ew) / 240          # updated AFTER use: only the past counts
            tk = ticks.get(ts[i])
            tk_usual = ew_tick
            if tk is not None:
                ew_tick = tk if ew_tick is None else ew_tick + (tk - ew_tick) / 240
            if usual is None or usual == 0 or i - last_imp < GAP:
                continue
            for K in KS:
                if a < max(K * usual, FLOOR[sym]):
                    continue
                if K == KS[0]:
                    last_imp = i
                busy = None
                if tk is not None and tk_usual:
                    busy = "sıx" if tk >= 2 * tk_usual else "adi"
                for H in HS:
                    j0, t1 = i + 1, ts[i] + 60 * (1 + H)
                    j1 = idx.get(t1)
                    if j0 >= len(rows) or ts[j0] != ts[i] + 60 or j1 is None:
                        continue
                    move = cs[j1] / cs[j0] - 1
                    net = (move if r > 0 else -move) - full_cost(sym)
                    cont = (move > 0) == (r > 0) and move != 0
                    for key in ((K, H, "hamısı"),) + (((K, H, busy),) if busy else ()):
                        res.setdefault(key, []).append((cont, net))
        rows_out = []
        for (K, H, grp), v in sorted(res.items()):
            n = len(v)
            hits = sum(c for c, _ in v)
            rows_out.append({"K": K, "H": H, "group": grp, "n": n, "continues": round(hits / n, 3),
                             "net_avg": round(sum(x for _, x in v) / n, 6), "p": _p_two(hits, n)})
        out["metals"][sym] = {"minutes": len(rows), "rows": rows_out}
    return out
