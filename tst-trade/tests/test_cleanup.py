"""Təmizlik: the retired methods' replayed history goes in batches, their record is kept, live rows and the methods in
use are untouched; a new rule version replays its history cleanly (old replayed rows do not mix in)."""
from app import cleanup, rules
from app.db import DB


def _row(db, method, mode, t, hit=1):
    db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, lo80, "
               "hi80, basis, hit, in80) VALUES('XAU','1h',?,?,?,?,1,0.6,1,1,1,1,'',?,1)", (method, mode, t, t + 3600, hit))


def test_retired_history_goes_and_the_record_stays():
    db = DB(":memory:")
    for t in range(50):
        _row(db, "momentum", "history", t)
        _row(db, "rw", "history", t)
    _row(db, "momentum", "live", 999)
    cleanup.BATCH = 7
    out = cleanup.retired_archive(db, pause=0)
    assert out["deleted"] == 50 and "momentum" in out["methods"]
    left = {r["method"] + "/" + r["mode"]: r["n"] for r in db.execute(
        "SELECT method, mode, COUNT(*) n FROM forecasts GROUP BY method, mode").fetchall()}
    assert left == {"momentum/live": 1, "rw/history": 50}
    import json
    rec = json.loads(db.get("archive:retired"))[0]["rows"]
    assert any(r["method"] == "momentum" and r["mode"] == "history" and r["n"] == 50 and r["hit_rate"] == 1.0 for r in rec)
    assert cleanup.retired_archive(db)["deleted"] == 50          # once only


def test_new_rule_version_deletes_old_replayed_rows_only():
    db = DB(":memory:")
    rules.ensure(db)
    db.executemany("INSERT INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note) VALUES(?,?,?,?,?,?,?,?,?)",
                   [("XAU", "1h", 1, "TA-OLD-1", 1, 1, 1, "history", ""), ("XAU", "1h", 2, "TA-OLD-1", 1, 1, 1, "live", ""),
                    ("XAU", "1h", 3, "FA-RY-1", 1, 1, 1, "history", ""), ("XAU", "1h", 4, "TA-X", 1, 1, 1, "futures", "")])
    db.execute(rules.TA_HISTORY_SQL, ("XAU", "1h"))
    left = {(r["t"], r["mode"]) for r in db.execute("SELECT t, mode FROM rule_signals").fetchall()}
    assert left == {(2, "live"), (3, "history"), (4, "futures")}
