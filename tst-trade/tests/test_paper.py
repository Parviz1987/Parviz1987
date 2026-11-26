"""Kağız ticarət: the risk engine rejects with a reason; the simulator fills with costs; stop first; emergency stop."""
from app import paper
from app.db import DB


def _db():
    db = DB(":memory:")
    paper.ensure(db)
    return db


def _bar(db, t, o, h, l, c):
    db.execute("INSERT INTO candles(symbol, tf, t, o, h, l, c, v) VALUES('XAU','1m',?,?,?,?,?,0)", (t, o, h, l, c))


T = 1_800_000_000.0


def test_accept_and_size_by_risk():
    db = _db()
    r = paper.propose(db, "XAU", "1d", "x", 0.7, 3500.0, 5, 3450.0, 3550.0, T + 86400, T)
    assert r["status"] == "açıq"
    assert 0.9 < r["oz"] <= 1.0                   # $50 risk / ($50 stop + cost) ≈ 0.99 oz
    assert r["entry"] > 3500 and r["target"] > r["entry"] and r["stop"] == 3450


def test_rejections_are_journalled_with_the_reason():
    db = _db()
    assert paper.propose(db, "XAU", "1d", "x", 0.7, 3500.0, 600, 3450, 3550, T + 86400, T)["reason"] == "qiymət köhnədir"
    paper.propose(db, "XAU", "1d", "x", 0.7, 3500.0, 5, 3450, 3550, T + 86400, T)
    assert "açıq mövqe" in paper.propose(db, "XAU", "1d", "x", 0.7, 3500.0, 5, 3450, 3550, T + 86400, T)["reason"]
    paper.emergency(db, True)
    assert paper.propose(db, "XAG", "1d", "x", 0.3, 40.0, 5, 39, 41, T + 86400, T)["reason"] == "təcili dayanma açıqdır"
    assert sum(1 for o in paper.view(db)["orders"] if o["status"] == "rədd") == 3


def test_stop_first_when_one_minute_touches_both_and_gap_fills_worse():
    db = _db()
    paper.propose(db, "XAU", "1d", "x", 0.7, 3500.0, 5, 3450, 3550, T + 86400, T)
    t = T - T % 60 + 60
    _bar(db, t, 3500, 3600, 3400, 3500)           # touches both: the stop counts
    paper.manage(db, t + 120)
    o = paper.view(db)["orders"][0]
    assert o["status"] == "bağlandı" and o["pnl"] < -45 and "stop" in o["reason"]
    db2 = _db()
    paper.propose(db2, "XAU", "1d", "x", 0.7, 3500.0, 5, 3450, 3550, T + 86400, T)
    _bar(db2, t, 3400, 3410, 3390, 3405)          # opens past the stop
    paper.manage(db2, t + 120)
    o = paper.view(db2)["orders"][0]
    assert o["exit"] < 3401 and "boşluq" in o["reason"]


def test_target_and_horizon_end_and_daily_limit():
    db = _db()
    r = paper.propose(db, "XAU", "1d", "x", 0.7, 3500.0, 5, 3450, 3550, T + 86400, T)
    t = T - T % 60 + 60
    _bar(db, t, 3500, r["target"] + 1, 3499, 3540)
    paper.manage(db, t + 120)
    v = paper.view(db)
    assert v["orders"][0]["pnl"] > 40 and v["stats"]["win_rate"] == 1.0 and v["equity"] > 10000
    paper.propose(db, "XAU", "1h", "x", 0.3, 3500.0, 5, 3450, 3550, t + 600, t + 60)
    _bar(db, t + 540, 3500, 3501, 3499, 3500)
    paper.manage(db, t + 700)
    assert "üfüq bitdi" in paper.view(db)["orders"][0]["reason"]
    db.execute("UPDATE paper_orders SET pnl=-500 WHERE horizon='1h'")
    assert paper.propose(db, "XAG", "1d", "x", 0.7, 40.0, 5, 39, 41, t + 86400, t + 800)["reason"] == "günlük zərər limiti doldu"


def test_settings_are_checked():
    db = _db()
    assert paper.set_settings(db, {"risk_pct": 1})["risk_pct"] == 1
    try:
        paper.set_settings(db, {"risk_pct": 50})
        assert False
    except ValueError:
        pass


def test_step_waits_without_al_sat_and_acts_on_one():
    import time
    from app.engine import Engine
    from app.keys import KeyStore
    db = DB(":memory:")
    eng = Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    now = time.time()
    paper.step(db, eng, {"XAU": {"desks": [{"horizon": "1d", "call": "GÖZLƏ", "p_up": 0.5}]}}, now)
    assert paper.view(db)["orders"] == []
    db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, lo80, "
               "hi80, basis) VALUES('XAU','1d','rw','live',?,?,3500,0.5,3480,3520,3450,3550,'')", (now - 60, now + 86400))
    eng.quotes = {"XAU": {"price": 3500.0, "recv_ts": now}}
    paper.step(db, eng, {"XAU": {"desks": [{"horizon": "1d", "call": "AL", "p_up": 0.7, "method": "m"}]}}, now)
    assert paper.view(db)["open"][0]["symbol"] == "XAU"


def test_outlook_scenarios_and_evidence():
    from app import outlook
    rw = {"price0": 100.0, "lo50": 99, "hi50": 101, "lo80": 98, "hi80": 102}
    tw = outlook.three_way(0.6, rw, 0.002)
    sc = outlook.scenarios(rw, tw)
    assert [x["name"] for x in sc] == ["yuxarı", "aralıq", "aşağı"] and abs(sum(x["p"] for x in sc) - 1) < 1e-3
    fc = {"qaydalar": {"p_up": 0.6, "basis": "TA up"}, "xeber": {"p_up": 0.4, "basis": "news down"},
          "rw": {"p_up": 0.5, "basis": ""}}
    ev = outlook.evidence(fc, 1)
    assert ev["pro"][0]["block"] == "texniki analiz" and ev["con"][0]["block"] == "xəbər"


def test_llm_json_with_text_after_the_object():
    from app import llm
    assert llm._json('{"found": false, "actual": ""}\nI could not find the release.') == {"found": False, "actual": ""}
    assert llm._json('Here: {"a": 1} done') == {"a": 1}
    import pytest
    with pytest.raises(llm.LLMError):
        llm._json('{"found": false, "actual": "')


def test_owner_policy_limits_one_method_and_the_fall_from_the_peak():
    from app import paper
    db = DB(":memory:")
    now = 1_800_000_000.0
    r = paper.propose(db, "XAU", "1h", "tsmom", 0.6, 2000.0, 5, 1980.0, 2020.0, now + 3600, now, size=0.25, cap=0.25)
    assert r["status"] == "açıq" and r["oz"] * 2000.0 <= 0.25 * 10000.0 + 1e-6
    db.execute("INSERT INTO paper_orders(ts, symbol, horizon, method, dir, oz, entry, stop, target, expires, status, "
               "reason, pnl, exit_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (now, "XAG", "1h", "x", 1, 1, 30, 29, 31, now, "bağlandı", "", -1200.0, now - 86400 * 3))
    r2 = paper.propose(db, "XPT", "1h", "tsmom", 0.6, 1000.0, 5, 990.0, 1010.0, now + 3600, now)
    assert r2["status"] == "rədd" and "zirvədən" in r2["reason"] and paper.settings(db)["stopped"]


def test_released_stop_measures_the_fall_afresh():
    from app import paper
    db = DB(":memory:")
    now = 1_800_000_000.0
    db.execute("INSERT INTO paper_orders(ts, symbol, horizon, method, dir, oz, entry, stop, target, expires, status, "
               "reason, pnl, exit_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (now, "XAG", "1h", "x", 1, 1, 30, 29, 31, now, "bağlandı", "", -1200.0, now - 86400 * 3))
    assert paper._peak_drawdown(db, paper.settings(db)) > 0.1
    paper.emergency(db, False)                                     # the owner releases the stop
    assert paper._peak_drawdown(db, paper.settings(db)) == 0.0
