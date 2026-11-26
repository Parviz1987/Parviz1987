"""Avtomatik Hakim siyasəti: the score is the weakest of its parts; the ladder follows the score alone; a strong
record gets a small paper share before it is proven and the full share only with the final test; the lag test
clears a real slow edge and not a method that read its own target candle; the decision layer trades the small step."""
import random

from app import autojudge as aj, rigor
from app.db import DB


def test_score_is_the_weakest_part_and_the_ladder_follows_it():
    random.seed(1)
    strong = [random.gauss(0.002, 0.008) for _ in range(600)]
    s = aj.score_method(strong, 0.03, 1, 250, 50)
    assert s["score"] == min(s["parts"].values()) and s["score"] >= 70
    assert aj.stage(s["score"], False) in (aj.SMALL, aj.FULL) and aj.stage(90, False) == aj.SMALL
    assert aj.stage(90, True) == aj.FULL and aj.stage(60, True) == aj.SHADOW and aj.stage(10, True) == aj.OFF
    weak = [random.gauss(0.0, 0.008) for _ in range(600)]
    assert aj.score_method(weak, 0.0, 1, 250, 50)["score"] < 50
    assert aj.size_factor(aj.SMALL, 80, 1.0) == 0.2 and aj.size_factor(aj.SHADOW, 80, 1.0) == 0.0
    assert aj.exposure_cap(10.0) == aj.MAX_SHARE and aj.exposure_cap(0.1) == 0.05


def test_lag_test_tells_a_leak_from_a_slow_edge():
    db = DB(":memory:")
    random.seed(2)
    step, t0 = 3600, 1_800_000_000 // 3600 * 3600
    c, closes = 100.0, []
    for i in range(800):
        c *= 1 + random.gauss(0, 0.002)
        closes.append(c)
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES('XAU','1h',?,?,?,?,?,'history')",
                   [(t0 + i * step, x, x, x, x) for i, x in enumerate(closes)])
    leak, slow = [], []
    for i in range(1, 700):
        t = t0 + i * step                           # issued at t, target candle labelled t (closes at t + step)
        p0, p1 = closes[i - 1], closes[i]
        leak.append({"issued_t": t, "target_t": t + step, "p_up": 0.7 if p1 > p0 else 0.3, "price0": p0, "price1": p1})
        nxt = closes[i + 1] > p1                    # a «slow» edge: also right about the following candle
        slow.append({"issued_t": t, "target_t": t + step, "p_up": 0.7 if nxt else 0.3, "price0": p0, "price1": p1})
    assert not rigor.lag_test(db, "XAU", "1h", leak, 0.5)["cleared"]
    assert rigor.lag_test(db, "XAU", "1h", slow, 0.5)["cleared"]
