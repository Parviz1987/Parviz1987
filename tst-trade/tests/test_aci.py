"""Aralığın tənzimlənməsi: when the market gets wilder than the range expects, the corrected range keeps ~80 % while
the plain one falls; when it is calmer, the corrected range narrows; outcomes are learned only once known."""
import math
import random

from app import aci


def _rows(n, vol_of, half=1.2816):
    random.seed(5)
    out = []
    for i in range(n):
        t = i * 3600
        z = random.gauss(0, vol_of(i))
        out.append({"issued_t": t, "target_t": t + 3600, "price0": 100.0, "price1": 100.0 * math.exp(z / 100),
                    "lo80": 100.0 * math.exp(-half / 100), "hi80": 100.0 * math.exp(half / 100), "gamma": 0.02})
    return out


def test_wilder_market_keeps_80_percent_with_the_correction():
    r = aci.replay(_rows(3000, lambda i: 1.0 if i < 1000 else 1.6))
    assert r["now_cover"] < 0.70 and abs(r["aci_cover"] - 0.80) < 0.04 and r["m_now"] > 1.3


def test_calmer_market_narrows():
    r = aci.replay(_rows(3000, lambda i: 0.6))
    assert r["now_cover"] > 0.95 and r["m_now"] < 0.8 and abs(r["aci_cover"] - 0.80) < 0.05
