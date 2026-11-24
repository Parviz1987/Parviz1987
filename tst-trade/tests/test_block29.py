import time

from app import cards, learning
from app.db import DB


def test_proposals_decided_after_a_week(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    db.script(learning.PROPOSALS_SCHEMA)
    now = time.time()
    db.execute("INSERT INTO rule_proposals(ts, text, status) VALUES(?,?,?)", (now - 8 * 86400, "dərs", "sınaqda"))
    db.execute("INSERT INTO rule_proposals(ts, text, status) VALUES(?,?,?)", (now - 86400, "təzə", "sınaqda"))
    assert learning.judge_proposals(db, now) == 1
    st = {r["text"]: r["status"] for r in db.execute("SELECT text, status FROM rule_proposals").fetchall()}
    assert st["dərs"].startswith("rədd") and st["təzə"] == "sınaqda"
    assert learning.accepted_rules(db) == []
    db.execute("UPDATE rule_proposals SET status='qəbul (A/B-də daha yaxşı)' WHERE text='dərs'")
    assert learning.accepted_rules(db)[0]["area"] == "Öyrənilmiş"


def test_cards_keep_cited_rules(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    data = {"metals": [{"symbol": "XAU", "p1h": 0.6, "p4h": 0.5, "p1d": 0.45, "why": "x", "counter": "y",
                        "invalidation": "z", "next_update": "w", "rules": ["TA-FIB-1", "NOT-A-RULE", "FA-RY-1"]}]}
    cards.freeze(db, 1_800_000_000.0, "strateq", data, "anthropic · m", "{}", "sys")
    assert cards.recent(db, "XAU")[0]["rules"] == "TA-FIB-1,FA-RY-1"
    db.execute("UPDATE forecast_cards SET scored_ts=?, result='düz', known_ts=?", (time.time(), time.time()))
    assert cards.rule_record(db)["TA-FIB-1"]["strateq"] == [3, 0]
