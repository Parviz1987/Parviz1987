"""Fərziyyə agenti: the template is strict, HY rules are filters of a base rule, counted as attempts, and never vote
before the owner's approval (and then only with firings after the idea was born)."""
import asyncio
import json

from app import ideas, rigor, rules
from app.db import DB
from app.engine import Engine
from app.keys import KeyStore

T0 = 1_700_000_000


def _db():
    db = DB(":memory:")
    Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    rules.ensure(db)
    rows = []
    for i in range(300):
        t = T0 + i * 3600
        d = 1 if i % 2 else -1
        rows.append(("XAU" if i % 3 else "XAG", "1h", t, "TA-BRK-1", d, 100.0, 101.0 if d > 0 else 99.5, "history",
                     "", 1.0, 2.0 if d > 0 else -1.0, 5, 30.0 if i % 4 else 10.0))
        if i % 5 == 0:
            rows.append(("XAU" if i % 3 else "XAG", "1h", t - 3600, "TA-ADX-1", d, 100.0, 100.5, "history", "", 1.0, 0.0, 5, 30.0))
    db.executemany("INSERT INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note, atr, rr, held, adx) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return db


RAW = {"base": "TA-BRK-1", "tf": "1h", "metals": [], "dir": 1, "adx": [2], "hour_from": -1, "hour_to": -1,
       "confirm_rule": "", "confirm_within": 0, "fa_context": False, "why": "trendd", "expect": "x"}


def test_template_is_strict():
    db = _db()
    ideas.ensure(db)
    rec = rules.records(db)["rules"]
    assert ideas.validate(db, {**RAW, "dir": 0, "adx": []}, rec)[1].startswith("heç bir süzgəc")
    assert "tapılmadı" in ideas.validate(db, {**RAW, "base": "TA-NOPE"}, rec)[1]
    assert "saat" in ideas.validate(db, {**RAW, "hour_from": 25, "hour_to": 3}, rec)[1]
    assert ideas.validate(db, {**RAW, "base": "HY-1"}, rec)[0] is None
    spec, _ = ideas.validate(db, RAW, rec)
    assert spec == {"base": "TA-BRK-1", "tf": "1h", "metals": [], "dir": 1, "adx": [2], "hours": None, "confirm": None,
                    "fa": False}


def test_hy_rule_is_a_filter_counted_and_measured():
    db = _db()
    ideas.ensure(db)
    rec = rules.records(db)["rules"]
    n0 = rigor.trials(db)
    spec, _ = ideas.validate(db, RAW, rec)
    rule = ideas.add(db, spec, "trend", "x", "test", now=T0 + 400 * 3600)
    rows = db.execute("SELECT dir, adx FROM rule_signals WHERE rule=?", (rule,)).fetchall()
    assert rows and all(r["dir"] == 1 and r["adx"] > 25 for r in rows)
    assert rigor.trials(db) == n0 + 1
    assert ideas.validate(db, RAW, rec)[1] == "bu fikir artıq sınaqdadır"
    assert rule in rules.records(db)["rules"]
    # confirmation filter: only firings with TA-ADX-1 in the same direction within 2 candles
    spec2, _ = ideas.validate(db, {**RAW, "dir": 0, "adx": [], "confirm_rule": "TA-ADX-1", "confirm_within": 2}, rec)
    r2 = ideas.add(db, spec2, "", "", "test")
    assert 0 < db.execute("SELECT COUNT(*) n FROM rule_signals WHERE rule=?", (r2,)).fetchone()["n"] < 100


def test_no_vote_before_approval_and_no_history_vote_after():
    db = _db()
    ideas.ensure(db)
    rec = rules.records(db)["rules"]
    spec, _ = ideas.validate(db, RAW, rec)
    rule = ideas.add(db, spec, "", "", "test", now=T0 + 150 * 3600)
    lk = rules.Lookup(db)
    assert not any(x[2] == rule for v in lk.fire.values() for x in v)
    rigor.register(db, "rule", rule, "*", "1h")
    db.execute("UPDATE strategy_registry SET status='təsdiqlənib' WHERE name=?", (rule,))
    lk = rules.Lookup(db)
    ts = [x[0] - 3600 for v in lk.fire.values() for x in v if x[2] == rule]
    assert ts and min(ts) > T0 + 150 * 3600
    assert lk.families[rule] == rules.RULE_FAMILY["TA-BRK-1"]


class _Keys:
    def first(self, p):
        return None


def test_tick_records_rejected_ideas_and_waits_a_week(monkeypatch):
    db = _db()
    from app import brains

    async def fake(db_, keys, slot, system, user, schema, max_tokens=0):
        assert slot == "ideas" and "TA-BRK-1" in user
        return {"ideas": [RAW, {**RAW, "base": "TA-NOPE"}, {**RAW, "dir": -1}]}, "fake"
    monkeypatch.setattr(brains, "run", fake)
    SUN = 1_700_402_400                   # Sunday 2023-11-19 14:00 UTC
    assert asyncio.run(ideas.tick(db, _Keys(), SUN - 3600)) == 0
    assert asyncio.run(ideas.tick(db, _Keys(), SUN)) == 1
    v = ideas.view(db)
    assert [x["status"] for x in v] == ["rədd", "sınaqda"] and "tapılmadı" in v[0]["reason"]
    assert asyncio.run(ideas.tick(db, _Keys(), SUN + 3600)) == 0
    assert json.loads(v[1]["spec"])["dir"] == 1
