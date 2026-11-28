"""Alış-satış planı (owner 28.11, stages 2 and 3): a resting limit at the corridor's edge fills when the window's low
reaches it, else the buyer buys at the window's close; savings against the same window's close; futures size from the
stop distance."""
from datetime import datetime, timezone

from app import plan
from app.db import DB


def _db(days):
    db = DB(":memory:")
    t0 = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    for k, (lo, hi, close) in enumerate(days):
        t = t0 + k * 86400
        db.execute("INSERT INTO candles(symbol, tf, t, o, h, l, c) VALUES('XAU','1d',?,?,?,?,?)", (t, 100, hi, lo, close))
        db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, "
                   "lo80, hi80, price1) VALUES('XAU','1d','vahid','history',?,?,100,0.5,99,101,98,102,?)", (t, t + 86400, close))
    return db


def test_a_limit_that_fills_saves_and_one_that_does_not_buys_at_the_close():
    db = _db([(98.5, 100.5, 100.0)] * 20 + [(99.5, 101.5, 101.0)] * 20)   # 20 days reach 99, 20 days do not
    out = plan.physical(db, "XAU", "1d")
    p1 = out["P1"]
    assert p1["n"] == 40 and p1["fill_rate"] == 0.5
    assert p1["mean_saving_pct"] == round((20 * (100 - 99) / 100 + 20 * 0) / 40 * 100, 4)   # 1 % on filled days
    assert out["P2"]["fill_rate"] == 0.0                                  # 98 never reached


def test_the_touch_rates_are_measured_on_the_path_not_the_close():
    db = _db([(97.5, 100.5, 100.0)] * 40)                                # every day dips below 98 and closes at 100
    t = plan.touches(db, "XAU", "1d")
    assert t["lo80"] == 1.0 and t["close_below_lo80"] == 0.0


def test_the_futures_size_keeps_the_loss_within_the_budget():
    s = plan.size(capital=20000, risk_pct=1.0, entry=4000.0, stop=3950.0, contract="MGC")    # $500 per MGC at the stop
    assert s["contracts"] == 0 and s["budget"] == 200.0
    s = plan.size(capital=100000, risk_pct=2.0, entry=4000.0, stop=3960.0, contract="MGC")   # $400 per contract
    assert s["contracts"] == 5 and s["loss_at_stop"] == 2000.0
