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


def test_focus_hypotheses_start_empty(tmp_path):
    from app import hypotheses
    db = DB(str(tmp_path / "t.db"))
    rows = hypotheses.evaluate_focus(db)
    assert [r["id"] for r in rows] == ["H9", "H10", "H12", "H13", "H11"] and all(r["status"] == "az" for r in rows)


def test_checker_allows_rounding_not_invention():
    given = '{"price": 4012.35, "rsi": 0.42}'
    assert checker.invented("Səviyyə 4012, RSI 0.4, 3 qayda", given) == []
    assert checker.invented("hədəf 4300", given) == ["4300"]


def test_v_family_starts_empty(tmp_path):
    from app import hypotheses
    db = DB(str(tmp_path / "v.db"))
    rows = hypotheses.evaluate_v(db)
    assert [r["id"] for r in rows] == ["V1", "V2", "V3", "V4", "V5", "Q1", "Q2", "Q3"]
    assert all(r["status"] == "az" for r in rows)


def test_q_family_counts_only_forecasts_after_its_registration_on_money(tmp_path):
    # plan 27.11 step 3.4: chosen by looking at the live record, so only NEW forecasts count, against 0.05 / 3
    from app import hypotheses
    db = DB(str(tmp_path / "q.db"))
    t0 = hypotheses.Q_REGISTERED
    for i in range(80):
        for before in (True, False):
            t = (t0 - 400 * 3600 if before else t0) + i * 3600
            up = i % 5 != 0                                   # right 4 times in 5, in the forecast's direction
            db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, price1, p_up, "
                       "lo50, hi50, lo80, hi80) VALUES('XAU', '1h', 'qaydalar', 'live', ?, ?, 100, ?, 0.6, 1, 1, 1, 1)",
                       (t, t + 3600, 100.5 if up else 99.7))
    q1 = next(r for r in hypotheses.evaluate_v(db) if r["id"] == "Q1")
    assert q1["n"] == 80 and q1["registered"] == t0 and abs(q1["p_bar"] - 0.05 / 3) < 1e-12
    assert q1["status"] == "sübut" and q1["net_avg"] > 0
