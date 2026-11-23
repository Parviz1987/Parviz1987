from app import simulator


def c(t, o, h, l, cl):
    return {"t": t, "o": o, "h": h, "l": l, "c": cl}


F = {"price0": 100.0, "p_up": 0.6, "lo80": 98.0, "hi80": 102.0, "lo50": 99.0, "hi50": 101.0, "price1": 100.5}


def test_long_hits_target_stop_or_time():
    assert simulator.play(F, [c(0, 100, 101.2, 99.5, 101)], 0.0)["how"] == "target"
    r = simulator.play(F, [c(0, 100, 100.5, 97.5, 98)], 0.0)
    assert r["how"] == "stop" and abs(r["ret"] - (98 / 100 - 1)) < 1e-12
    r = simulator.play(F, [c(0, 100, 100.6, 99.6, 100.5)], 0.001)
    assert r["how"] == "time" and abs(r["ret"] - (0.005 - 0.001)) < 1e-12


def test_pessimistic_and_gaps_and_short():
    both = [c(0, 100, 101.5, 97.5, 100)]
    assert simulator.play(F, both, 0.0)["how"] == "stop"                     # unknown order: the stop counts
    gap = simulator.play(F, [c(0, 97, 97.5, 96, 97)], 0.0)                    # opens through the stop
    assert abs(gap["ret"] - (97 / 100 - 1)) < 1e-12
    short = simulator.play({**F, "p_up": 0.4}, [c(0, 100, 100.2, 98.8, 99)], 0.0)
    assert short["how"] == "target" and short["ret"] > 0
    assert simulator.play({**F, "p_up": 0.5}, both, 0.0) is None              # no direction: no trade


def test_simulate_proves_only_real_money():
    from app import candles
    from app.db import DB
    db = DB(":memory:")
    rows, cs = [], []
    t = 1_700_006_400
    for i in range(300):
        ti = t + i * 3600
        cs.append((ti, 100, 100.6, 99.95, 100.55))      # every hour gold rises to the 50 % target, never to the stop
        for m, p in (("trend", 0.6), ("rsi", 0.4)):
            rows.append(("XAU", "1h", m, "history", ti, ti + 3600, 100.0, p, 99.7, 100.3, 99.0, 101.0, "", 100.55, 1.0))
    candles.store_history(db, "XAU", "1h", cs)
    db.executemany("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50,"
                   " lo80, hi80, basis, price1, scored_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    out = simulator.simulate(db, "XAU", "1h")["methods"]
    assert out["trend"]["status"] == "sübut" and out["trend"]["avg"] > 0
    assert out["rsi"]["status"] == "yox" and out["rsi"]["avg"] < 0
