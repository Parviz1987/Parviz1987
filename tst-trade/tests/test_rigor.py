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
