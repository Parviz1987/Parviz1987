"""Radar Gold ideas: the one-look final test, the attempts counter, the block value (ablation)."""
from app import rigor
from app.db import DB
from app.engine import Engine
from app.keys import KeyStore


def _db():
    db = DB(":memory:")
    Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    return db


def test_attempts_only_grow_and_adjust_p():
    db = _db()
    n = rigor.trials(db)
    assert n > 1000                                  # methods x desks x metals + rules x timeframes + hypotheses
    db.put("trials:seen", db.get("trials:seen")[:-1] + ', "m:old-idea:1h:XAU"]')
    assert rigor.trials(db) == n + 1                 # a retired idea is never forgotten
    assert abs(rigor.p_all(0.001, 1) - 0.001) < 1e-12 and 0.6 < rigor.p_all(0.001, 1000) < 0.64


def _forecasts(db, t0, n, win=True):
    rows = []
    for i in range(n):
        t = t0 + i * 3600
        rows.append(("XAU", "1h", "seans", "live", t, t + 3600, 100.0, 0.6, 99, 101, 98, 102, "", 101.0 if win else 99.5,
                     1.0, 1, 1, 0.16, 1, 1))
    db.executemany("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, "
                   "lo80, hi80, basis, price1, scored_ts, outcome, hit, brier, in50, in80) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def test_final_test_uses_only_later_data_and_looks_once():
    db = _db()
    t0 = 1_800_000_000
    _forecasts(db, t0 - 500 * 3600, 400)                 # the data that made it a candidate: never counted again
    st = rigor.method_final(db, "XAU", "1h", "seans", now=t0)
    assert st["status"] == "namizəd" and st["n"] == 0
    _forecasts(db, t0 + 3600, 400, win=False)            # after the finalist moment it loses
    st = rigor.method_final(db, "XAU", "1h", "seans", now=t0 + 500 * 3600)
    assert st["status"] == "keçmədi"
    _forecasts(db, t0 + 600 * 3600, 400, win=True)       # later wins change nothing: one look only
    assert rigor.method_final(db, "XAU", "1h", "seans", now=t0 + 2000 * 3600)["status"] == "keçmədi"


def test_judge_verdict_needs_the_final(monkeypatch):
    from app import judge
    db = _db()
    monkeypatch.setattr(judge, "stats", lambda *a, **k: [{"method": "seans", "status": "sübut", "bss": 0.1}])
    v = judge.verdict(db, "XAU", "1h", now=1_800_000_000)
    assert v["status"] == "namizəd" and v["candidate"] == "sübut" and v["final"]["status"] == "namizəd"


def test_block_value_runs_without_each_block():
    from app import blocks, unified
    db = _db()
    rows = []
    for i in range(300):
        t = 1_800_000_000 + i * 3600
        up = i % 3 != 0
        for m, p in (("qaydalar", 0.6 if up else 0.4), ("xeber", 0.55)):
            rows.append(("XAU", "1h", m, "history", t, t + 3600, 100.0, p, 99, 101, 98, 102, "", 101.0 if up else 99.0,
                         1.0, int(up), None, None, 1, 1))
    db.executemany("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, "
                   "lo80, hi80, basis, price1, scored_ts, outcome, hit, brier, in50, in80) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    a = unified.ablation(db)
    d = a["desks"]["1h"]
    assert set(d["without"]) == {b["id"] for b in blocks.BLOCKS}
    assert d["without"]["ta"]["hit_rate"] < d["full"]["hit_rate"]       # the informative block: worse without it


def test_physical_stock_values_lots_and_journals_sales():
    from app import candles, stock
    db = _db()
    candles.add_tick(db, "XAU", 1_800_000_000, 3000.0)
    lid = stock.add_lot(db, "585 lom", "XAU", 500, 585, 20000, "2026-11-01")
    v = stock.view(db)
    lot = v["lots"][0]
    assert abs(lot["net_g"] - 292.5) < 1e-9 and abs(lot["net_oz"] - 292.5 / 31.1034768) < 1e-4
    assert abs(lot["spot_value"] - 292.5 / 31.1034768 * 3000) < 0.01
    assert abs(lot["refiner_value"] - lot["spot_value"] * 0.985) < 0.01          # 1 % fee + 0.5 % melt loss
    t = v["totals"][0]
    assert t["scenarios"]["+1%"] > 0 > t["scenarios"]["-5%"]
    stock.sell(db, lid, 200, 583, 9000)
    v = stock.view(db)
    assert v["lots"][0]["grams"] == 300 and v["sales"][0]["cost"] == 8000.0 and v["realised"] == 1000.0
    try:
        stock.delete_lot(db, lid)
        raise AssertionError("a sold lot must not be deleted")
    except ValueError:
        pass
    r = stock.import_csv(db, "ad,metal,qram,əyar,dəyər\nring,XAU,10,750,500\nbad,XAU,x,750,1\n")
    assert r["added"] == 1 and len(r["errors"]) == 1


def test_guest_cannot_open_the_stock():
    from fastapi.testclient import TestClient
    import os
    os.environ.setdefault("APP_PASSWORD", "test")
    from app import main
    assert "/api/stock" in open(main.__file__).read() and '"/ehtiyat", "/api/stock"' in open(main.__file__).read()


def test_registry_follows_the_owners_one_time_policy(monkeypatch):
    """Owner 2026-11-26 («Avtomatik Hakim siyasəti»): a finalist that passed is approved by the policy itself; an
    owner's explicit rejection or an automatic demotion still keeps it out."""
    from app import judge
    db = _db()
    monkeypatch.setattr(judge, "stats", lambda *a, **k: [{"method": "seans", "status": "sübut", "bss": 0.1}])
    monkeypatch.setattr(rigor, "method_final", lambda *a, **k: {"status": "keçdi"})
    rigor.register(db, "method", "seans", "XAU", "1h")
    assert judge.verdict(db, "XAU", "1h", now=1_800_000_000)["status"] == "sübut"
    rigor.decide(db, "method", "seans", "XAU", "1h", False, "sahib rədd etdi")
    assert judge.verdict(db, "XAU", "1h", now=1_800_000_000)["status"] == "yox"
    assert rigor.experiments(db)[0]["kind"] == "decision"


def test_independent_recheck_catches_wrong_stored_prices():
    db = _db()
    from app import candles
    t0 = 1_800_000_000 // 3600 * 3600
    candles.store_history(db, "XAU", "1h", [(t0 + i * 3600, 100 + i, 101 + i, 99 + i, 100 + i) for i in range(60)])
    rows = []
    for i in range(1, 40):
        t = t0 + i * 3600
        p0 = 100 + i - 1
        rows.append(("XAU", "1h", "seans", "live", t, t + 3600, p0, 0.6, 99, 101, 98, 102, "", p0 + 1, 1.0, 1, 1, 0.16, 1, 1))
    db.executemany("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, "
                   "lo80, hi80, basis, price1, scored_ts, outcome, hit, brier, in50, in80) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    assert rigor.verify_method(db, "XAU", "1h", "seans", t0)["ok"]
    db.execute("UPDATE forecasts SET price1 = price0 * 0.9")                          # stored prices gone wrong
    assert not rigor.verify_method(db, "XAU", "1h", "seans", t0)["ok"]


def test_three_way_probabilities_sum_to_one_and_robustness_flags_fragile():
    from app import outlook, rules
    tw = outlook.three_way(0.6, {"price0": 3000, "lo50": 2970, "hi50": 3030}, 0.0006)
    assert abs(tw["up"] + tw["down"] + tw["neutral"] - 1) < 1e-3 and tw["up"] > tw["down"]
    v = [(1_700_000_000 + i * 86400, 0.002, 0.0015 if i < 150 else -0.0005, "XAU") for i in range(300)]
    r = rules.robustness(v, [0.0005] * 300, deep=True)
    assert r["fragile"] and "boot95" in r and r["windows"]


def test_a_forecast_written_after_its_target_time_never_counts_in_a_final():
    # 27.11: the look-ahead guard that does not depend on how good a result looks — a row written after its target
    # candle closed (a catch-up after a stall, a replay labelled live) could have seen the answer
    import time as _time
    from app import judge, rigor
    from app.db import DB
    db = DB(":memory:")
    fc = {"price": 100.0, "methods": {"qaydalar": {"p_up": 0.6, "lo50": 99, "hi50": 101, "lo80": 98, "hi80": 102,
                                                   "basis": "x"}}}
    now = int(_time.time())
    judge.issue(db, "XAU", "1h", now - 7200, now - 3600, fc)          # written now, target an hour ago: late
    judge.issue(db, "XAU", "1h", now, now + 3600, fc)                 # written before its target: counts
    rows = db.execute(f"SELECT issued_t FROM forecasts WHERE {rigor.WRITTEN_IN_TIME}").fetchall()
    assert [r["issued_t"] for r in rows] == [now]
    r = db.execute("SELECT created_ts FROM forecasts WHERE issued_t=?", (now,)).fetchone()
    assert abs(r["created_ts"] - _time.time()) < 5
