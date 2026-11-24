import math

from app import futstudy
from app.db import DB
from app.futures import ensure


def test_study_finds_continuing_heavy_impulses(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    ensure(db)
    t0, rows, px = 1_700_000_040, [], 2000.0
    for i in range(60000):
        t = t0 + 60 * i
        step = 0.0001 * math.sin(i * 1.7)                 # quiet wiggle
        vol = 100.0
        if i % 400 == 200:
            step, vol = 0.004, 900.0                     # a heavy impulse ...
        elif 200 < i % 400 <= 240:
            step = 0.0002                                # ... that keeps going for 40 minutes
        px *= 1 + step
        rows.append(("XAU", t, px, px, px, px, vol))
    db.executemany("INSERT INTO fut_candles VALUES(?,?,?,?,?,?,?)", rows)
    res = futstudy.run_and_store(db)
    assert res["check"]["XAU"]["n"] == 60000
    cell = next(x for x in res["metals"]["XAU"]["rows"]
                if x["K"] == 4.0 and x["H"] == 15 and x["group"] == "böyük həcm" and x["part"] == "cəmi")
    assert cell["n"] >= 100 and cell["continues"] == 1.0 and cell["net_futures"] > 0
    assert cell["verdict"] == "sübut" and cell["both_years"]
    s = futstudy.summary(db)
    assert s["metals"]["XAU"]["proven"]


def test_vwap_test_runs(tmp_path):
    from app import futstudy
    from app.db import DB
    from app.futures import ensure
    db = DB(str(tmp_path / "v.db"))
    ensure(db)
    rows = [("XAG", 1_700_002_800 + 60 * i, 25 + 0.001 * i, 25 + 0.001 * i, 25 + 0.001 * i, 25 + 0.001 * i, 10.0)
            for i in range(20000)]
    db.executemany("INSERT INTO fut_candles VALUES(?,?,?,?,?,?,?)", rows)
    res = futstudy.study(db)
    v = res["metals"]["XAG"]["vwap"]["cəmi"]
    assert v["n"] > 300 and v["continues"] == 1.0          # a steady rise: above VWAP and still rising
