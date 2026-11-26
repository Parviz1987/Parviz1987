"""Səhvin yarılması: Murphy separates a miscalibrated voice from one with no information; each miss gets one cause in
the fixed order; slices use a Bonferroni bar; the run never fails on an empty database."""
import random

from app import autopsy
from app.db import DB


def test_murphy_separates_calibration_from_no_information():
    random.seed(1)
    ys = [int(random.random() < 0.5) for _ in range(2000)]
    over = [0.9 if y else 0.1 for y in ys]                  # informative but over-confident
    over = [p if random.random() < 0.7 else 1 - p for p in over]
    noinfo = [0.5 + random.uniform(-0.01, 0.01) for _ in ys]
    a, b = autopsy.murphy(over, ys), autopsy.murphy(noinfo, ys)
    assert a["resolution"] > 0.05 and a["reliability"] > 0.02
    assert b["resolution"] < 0.002 and b["verdict"] == "ayırd etmə gücü yoxdur"


class D:
    def __init__(self, pct, z):
        self.pct, self.z = [pct], [z]

    def at(self, t):
        return 0


def test_causes_in_the_fixed_order():
    r = {"price0": 100.0, "price1": 103.0, "issued_t": 0}
    sig = 0.01                                               # the move is 3 sigma
    assert autopsy.cause(r, sig, "yan", False, D(0.5, 0.0), False) == "məlumat"
    assert autopsy.cause(r, sig, "şok", False, D(0.99, 0.0), True) == "tanış olmayan"
    assert autopsy.cause(r, sig, "hadisə", True, D(0.5, 0.0), True) == "təqvim"
    assert autopsy.cause(r, sig, "yan", False, D(0.5, 0.0), True) == "şok"
    small = {"price0": 100.0, "price1": 100.3, "issued_t": 0}
    assert autopsy.cause(small, sig, "yan", False, D(0.5, 0.0), True) == "səs-küy"
    turn = {"price0": 100.0, "price1": 100.8, "issued_t": 0}
    assert autopsy.cause(turn, sig, "trend", False, D(0.5, -1.4), True) == "rejim"


def test_bonferroni_bar_and_empty_run():
    assert 2.9 < autopsy._z_bonf(20) < 3.1
    out = autopsy.run(DB(":memory:"))
    assert out["totals"] == {c: 0 for c in autopsy.CAUSES} and out["hints"] == []
