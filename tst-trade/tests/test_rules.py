import math

from app import playbook, rules
from app.db import DB


def _candles(db, sym, tf, step, n, f):
    rows = []
    t0 = 1_780_000_000 // step * step
    for i in range(n):
        c = f(i)
        rows.append((sym, tf, t0 + step * i, c - 0.3, c + 1.0, c - 1.0, c))
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c) VALUES(?,?,?,?,?,?,?)", rows)


def test_replay_then_records(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    for sym, base in (("XAU", 2000.0), ("XAG", 25.0)):
        for tf, step in (("1h", 3600), ("4h", 14400), ("1d", 86400)):
            _candles(db, sym, tf, step, 700, lambda i, b=base: b * (1 + 0.0004 * i + 0.01 * math.sin(i / 9)))
    res = rules.run(db, now=1_900_000_000)
    assert res["replay"] and res["added"] > 0
    fired = {r["rule"] for r in db.execute("SELECT DISTINCT rule FROM rule_signals").fetchall()}
    assert "TA-TREND-1" in fired and fired <= set(playbook.BY_ID)
    rec = rules.records(db)
    assert "TA-TREND-1" in rec["rules"] and rec["rules"]["TA-TREND-1"]["1h"]["n"] > 0
    assert rules.run(db, now=1_900_000_000)["added"] == 0          # nothing twice
    assert isinstance(rules.short_records(rec)["TA-TREND-1"], str)
    assert rules.active_now(db, "XAU")


def test_playbook_text_and_ids_unique():
    ids = [r["id"] for r in playbook.RULES]
    assert len(ids) == len(set(ids))
    txt = playbook.text_for(("Fibonacci",), {"TA-FIB-1": "1h 52 %/300"})
    assert "TA-FIB-1" in txt and "Hakim: 1h 52 %/300" in txt and "FA-RY-1" not in txt
