import random

from app import unified
from app.db import DB


def test_walk_forward_learns_the_useful_analyst_without_look_ahead(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    rnd = random.Random(1)
    rows, px = [], 100.0
    for i in range(3000):
        t = 1_700_000_000 + 3600 * i
        up = rnd.random() < 0.5
        good = 0.62 if up else 0.38                 # «good» sees the next move
        noise = 0.62 if rnd.random() < 0.5 else 0.38
        p1 = px * (1.01 if up else 0.99)
        for m, p in (("good", good), ("noise", noise), ("rw", 0.5)):
            rows.append(("XAU", "1h", m, "history", t, t + 3600, px, p, px, px, px, px, "", p1, 1))
        px = p1
    db.executemany("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, "
                   "lo80, hi80, basis, price1, scored_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    r = unified.simulate(db, "XAU", "1h")
    assert r["weights"]["good"] > 5 * abs(r["weights"].get("noise", 0))
    assert r["hit_rate"] > 0.9 and r["n"] == unified.MAX_MOMENTS     # the newest whole moments
    v = unified.view(r, {"good": {"p_up": 0.62}, "noise": {"p_up": 0.38}})
    assert v["p_up"] > 0.55
    assert unified.view(None, {})["p_up"] == 0.5
