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
