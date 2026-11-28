"""Koridor mühərriki v2 (plan docs/PLAN-KORIDOR.md, stage 1): on a simulated market whose volatility changes in known
regimes, the corridor must hold its promised coverage, follow the volatility, and use no future data."""
import math
import random
from datetime import datetime, timedelta, timezone

from app import corridor
from app.db import DB


def _market(n=1600, seed=7):
    rnd = random.Random(seed)
    out, p, d = [], 2000.0, datetime(2019, 1, 1, tzinfo=timezone.utc)
    for k in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        vol = 0.006 if (k // 200) % 2 == 0 else 0.018                      # calm and wild regimes
        r = rnd.gauss(0, vol)
        o, c = p, p * math.exp(r)
        h = max(o, c) * math.exp(abs(rnd.gauss(0, vol * 0.6)))
        l = min(o, c) * math.exp(-abs(rnd.gauss(0, vol * 0.6)))
        out.append({"t": int(d.timestamp()), "o": o, "h": h, "l": l, "c": c})
        p, d = c, d + timedelta(days=1)
    return out


def test_the_corridor_keeps_its_promise_and_follows_volatility():
    b = _market()
    rows = [r for r in corridor.Engine(DB(":memory:"), "XAG", 1, b).run() if r["price1"] is not None]
    assert len(rows) > 900
    c80 = sum(r["lo80"] <= r["price1"] <= r["hi80"] for r in rows) / len(rows)
    c50 = sum(r["lo50"] <= r["price1"] <= r["hi50"] for r in rows) / len(rows)
    assert abs(c80 - 0.80) < 0.04 and abs(c50 - 0.50) < 0.05
    calm = [(r["hi80"] - r["lo80"]) / r["price"] for r in rows if (r["i"] // 200) % 2 == 0 and r["i"] % 200 > 40]
    wild = [(r["hi80"] - r["lo80"]) / r["price"] for r in rows if (r["i"] // 200) % 2 == 1 and r["i"] % 200 > 40]
    assert sum(wild) / len(wild) > 2 * sum(calm) / len(calm)        # wider when the market is wild


def test_no_future_data_is_used():
    """The corridor for bar i must not change when the bars after i change."""
    b = _market(900)
    a = {r["i"]: r for r in corridor.Engine(DB(":memory:"), "XAG", 5, b).run()}
    b2 = [dict(x) for x in b]
    for x in b2[700:]:
        x["c"] *= 1.3
        x["h"] *= 1.3
        x["l"] *= 1.3
    a2 = {r["i"]: r for r in corridor.Engine(DB(":memory:"), "XAG", 5, b2).run()}
    common = [i for i in a if i in a2 and i < 690]   # bars before 700 (minus the 5-day horizon) see only the past
    assert len(common) > 200
    for i in common:
        assert abs(a[i]["lo80"] - a2[i]["lo80"]) < 1e-9 and abs(a[i]["hi80"] - a2[i]["hi80"]) < 1e-9
