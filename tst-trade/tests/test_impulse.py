"""The impulse study: a sudden one-minute move, entered one minute later, measured net of the spread."""
from app import candles, impulse
from app.db import DB


def test_impulse_that_continues_is_counted_from_one_minute_later():
    db = DB(":memory:")
    t0 = 1_800_000_000 // 60 * 60
    px, rows = 1000.0, []
    for i in range(3000):
        if i % 200 == 100:
            px *= 1.003                       # an impulse: +0.3 % in one minute
        elif i % 200 in range(101, 131):
            px *= 1.0002                      # ...and it goes on for half an hour
        else:
            px *= 1.00002 if i % 2 else 0.99998
        rows.append((t0 + i * 60, px, px, px, px))
    candles.store_history(db, "XAU", "1m", rows)
    out = impulse.study(db, t0 + 3000 * 60)
    r = next(x for x in out["metals"]["XAU"]["rows"] if x["K"] == 4.0 and x["H"] == 15 and x["group"] == "hamısı")
    assert r["n"] >= 10 and r["continues"] == 1.0 and r["net_avg"] > 0
