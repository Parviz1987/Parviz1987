import math

from app import forecast, patterns


def c(o, h, l, cl, t=0):
    return {"t": t, "o": o, "h": h, "l": l, "c": cl}


def test_engulfing_after_fall_leans_up():
    seq = [c(110, 111, 109, 110), c(110, 110, 106, 107), c(107, 107, 104, 105), c(105, 105, 102, 103),
           c(103, 103.5, 100, 101), c(100.5, 104, 100, 103.5)]
    p, why = patterns.candle_pattern_view(seq)
    assert p > 0.5 and "udma" in why


def test_ichimoku_uptrend():
    seq = [c(100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(90)]
    assert patterns.ichimoku_view(seq)[0] > 0.5
    assert patterns.ichimoku_view(seq[:50])[0] == 0.5


def test_pair_extreme_ratio():
    g = [100.0] * 99 + [130.0]
    o = [10.0] * 100
    assert patterns.pair_view((g, o))[0] < 0.5
    assert patterns.pair_view(None)[0] == 0.5


def test_garch_and_gvz_ranges_bracket_price():
    rets = [0.01 * math.sin(i) for i in range(200)]
    r = forecast.garch_range(rets, 100.0, 1)
    assert r["lo80"] < r["lo50"] < 100 < r["hi50"] < r["hi80"]
    g = forecast.gvz_range(16.0, 4000.0, 1)
    assert abs(g["hi80"] / 4000 - 1 - (math.exp(1.2816 * 0.16 / math.sqrt(252)) - 1)) < 1e-9
    assert forecast.gvz_range(None, 4000.0, 1) is None


def test_build_keeps_own_ranges():
    seq = [c(100 + math.sin(i), 101 + math.sin(i), 99 + math.sin(i), 100 + math.sin(i), 1_700_000_000 + 86400 * i)
           for i in range(260)]
    fc = forecast.build(seq, "1d", related={"gvz": 15.0})
    m = fc["methods"]
    assert m["gvz"]["hi80"] != m["rw"]["hi80"] and m["garch"]["hi80"] != m["rw"]["hi80"]
    assert m["qaydalar"]["hi80"] == m["rw"]["hi80"]


def test_every_family_has_a_name():
    assert set(forecast.FAMILY.values()) <= set(forecast.FAMILY_NAMES)
