"""Blokların yoxlanması: every block gets a sheet; a block whose source is failing or whose voice had no view in 7
days is «qırıq», otherwise «zəif» until the Judge proves it."""
import json
import time

from app import blockaudit
from app.db import DB


def test_sheets_and_verdicts():
    db = DB(":memory:")
    db.put("src:rss", json.dumps({"ok": False, "checked": time.time() - 3600, "message": "HTTP 503"}))
    out = blockaudit.build(db)
    by = {b["id"]: b for b in out["blocks"]}
    assert set(by) >= {"ta", "fund", "news", "cross", "time", "brain"}
    assert by["news"]["verdict"] == "qırıq" and "rss" in by["news"]["why"]
    assert by["ta"]["verdict"] == "qırıq" and "fikri" in by["ta"]["why"]      # no forecasts at all in this test db
    assert blockaudit.view(db)["blocks"]


def test_news_waits_for_a_week_of_labels():
    db = DB(":memory:")
    db.execute("CREATE TABLE IF NOT EXISTS news_ai (uid TEXT PRIMARY KEY, ts REAL, event TEXT, metals TEXT, direction TEXT, "
               "strength INTEGER, brain TEXT)")
    db.execute("INSERT INTO news_ai VALUES('a', ?, 'fed', 'XAU', 'up', 2, 'x')", (time.time() - 2 * 86400,))
    by = {b["id"]: b for b in blockaudit.build(db)["blocks"]}
    assert by["news"]["verdict"] == "gözləyir" and by["news"]["labels"]["all"] == 1
