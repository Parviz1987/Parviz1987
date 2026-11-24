import json
import time

from app import cards
from app.db import DB


def test_quality_lists_missing_inputs():
    q = cards.quality({"moves_pct": {"XAU": {}}, "macro": {}, "news": []})
    assert "XAG: son hərəkət yoxdur" in q and "DXY: bazar məlumatı yoxdur" in q
    assert "makro göstəricilər yoxdur" in q


def test_freeze_and_score(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    now = 1_800_000_000.0
    data = {"metals": [{"symbol": "XAU", "p1h": 0.6, "p4h": 0.5, "p1d": 0.4, "why": "dollar zəifdir",
                        "counter": "güclü ABŞ rəqəmi", "invalidation": "DXY qalxsa", "next_update": "CPI-dən sonra"}]}
    n = cards.freeze(db, now, "strateq", data, "anthropic · claude-sonnet-5-5", json.dumps({"moves_pct": {}}), "sys")
    assert n == 3
    c = cards.recent(db, "XAU")[0]
    assert c["counter"] == "güclü ABŞ rəqəmi" and c["model"] == "claude-sonnet-5-5" and c["quality"]
    assert c["p_cal"] is None                         # not calibrated: shown as «not measured», never guessed
    assert cards.score(db, now + 2 * 86400) == 3     # no prices: scored as «ölçülmədi», not guessed
    assert {x["result"] for x in cards.recent(db, "XAU")} == {"ölçülmədi"}
