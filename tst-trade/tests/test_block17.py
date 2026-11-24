import time

from app import activity, checker, newsevents
from app.db import DB


def _news(db, uid, title, ts):
    db.execute("INSERT INTO news(uid, source, url, title, ts, metals) VALUES(?,?,?,?,?,?)", (uid, "s", "u", title, ts, ""))


def test_same_story_is_one_event(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    from app import feeds
    db.script(feeds.SCHEMA)
    now = time.time()
    _news(db, "a", "Fed holds rates steady, signals two cuts in 2027 - Reuters", now - 300)
    _news(db, "b", "Fed holds rates steady and signals two cuts in 2027 - CNBC", now - 200)
    _news(db, "c", "China central bank adds gold reserves for 14th month", now - 100)
    r = newsevents.assign(db, now)
    assert r == {"headlines": 3, "new_events": 2}
    ev = {x["uid"]: x["event_id"] for x in db.execute("SELECT uid, event_id FROM news_event").fetchall()}
    assert ev["a"] == ev["b"] != ev["c"]
    assert newsevents.assign(db, now)["headlines"] == 0          # nothing assigned twice


def test_checker_counts_invented_numbers(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    given = '{"moves_pct": {"XAU": {"1h": 0.42}}}'
    n = checker.record(db, "strategist", {"metals": [{"symbol": "XAU", "why": "Qızıl 0.42 % qalxdı, 3500-ə çatacaq",
                                                      "p1h": 0.61}]}, given)
    assert n == 1                                                  # 3500 was not given; 0.61 is structure, not text
    rep = checker.report(db)
    assert rep[0]["slot"] == "strategist" and rep[0]["invented"] == 1 and rep[0]["bad_share"] == 1


def test_hub_sequence_and_source(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    hub = activity.Hub(db)
    hub.report("reader", "working")
    hub.report("strateq", "done", src="signals")
    ev = hub.events(0)
    assert [e["seq"] for e in ev] == [1, 2]
    assert ev[0]["src"] == "events" and ev[1]["src"] == "signals"
    assert activity.Hub(db).seq == 2                               # numbering continues after a restart
