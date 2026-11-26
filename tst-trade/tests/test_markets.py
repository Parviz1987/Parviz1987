"""The old impulse methods became the cross-market rule CM-USD-2 / CM-OIL-1: a linked market moved and the metal has
not followed yet; of the dollar markets the one most linked to the metal is used."""
import math
import random

from app import crossmarket as cm, forecast


def _pair(n=140, beta=1.0, seed=2, noise=0.0002):
    rng = random.Random(seed)
    x, g = [100.0], [100.0]
    for _ in range(n):
        r = rng.gauss(0, 0.001)
        x.append(x[-1] * math.exp(r))
        g.append(g[-1] * math.exp(beta * r + rng.gauss(0, noise)))
    return x, g


def test_catch_up_sees_a_move_the_metal_has_not_followed():
    x, g = _pair()
    x[-1] = x[-2] * math.exp(0.004)                 # the market jumps, the metal stays
    g[-1] = g[-2]
    out = cm.detect("XAU", len(g) - 1, {"_metal": cm.Series(g), "EURUSD": cm.Series(x)})
    assert ("CM-USD-2", 1) in [(r, d) for r, d, _ in out]
    g[-1] = g[-2] * math.exp(0.004)                 # the metal followed: no catch-up
    out = cm.detect("XAU", len(g) - 1, {"_metal": cm.Series(g), "EURUSD": cm.Series(x)})
    assert "CM-USD-2" not in [r for r, _, _ in out]


def test_the_most_linked_dollar_market_is_used_and_old_methods_are_retired():
    x, g = _pair()
    noise = [100.0 * math.exp(random.Random(9).gauss(0, 0.001) * k) for k in range(len(g))]
    x[-1] = x[-2] * math.exp(0.004)
    g[-1] = g[-2]
    out = cm.detect("XAU", len(g) - 1, {"_metal": cm.Series(g), "DXY": cm.Series(noise), "EURUSD": cm.Series(x)})
    assert any(r == "CM-USD-2" and "EURUSD" in note for r, _, note in out)
    assert {"dollar", "oil", "risk", "seans"} <= set(forecast.RETIRED)
    assert not {"dollar", "oil", "risk", "seans"} & set(forecast.METHODS)
