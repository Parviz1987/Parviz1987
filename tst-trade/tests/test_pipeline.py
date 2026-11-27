from app import pipeline
from app.brainjobs import BrainJobs
from app.db import DB
from app.engine import Engine
from app.feeds import Feeds
from app.keys import KeyStore


def test_pipeline_lists_every_link_and_spots_a_stalled_reader():
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    feeds = Feeds(db, ks)
    jobs = BrainJobs(db, ks, feeds)
    eng = Engine(db, ks, "demo", 15, feeds, jobs)
    now = 1_795_442_400.0                     # a Monday, market open
    for i in range(12):                       # headlines nobody labelled for over 15 minutes
        db.execute("INSERT INTO news(uid, source, url, title, ts, metals) VALUES(?,?,?,?,?,?)",
                   (f"u{i}", "x", "", f"t{i}", now - 3000 - i, "XAU"))
    rows = pipeline.check(db, ks, eng, feeds, jobs, now)
    stages = {r["stage"]: r for r in rows}
    assert stages["Oxuyucu (başlıqları qiymətləndirir)"]["status"] == "warn"
    assert stages["Qiymət axını (4 metal)"]["status"] == "bad"      # no prices arrived
    assert all({"stage", "into", "status", "msg"} <= set(r) for r in rows)
    assert "Oxuyucu (başlıqları qiymətləndirir)" in pipeline.summary(rows)["warn"]


def _setup():
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    feeds = Feeds(db, ks)
    jobs = BrainJobs(db, ks, feeds)
    return db, ks, feeds, jobs, Engine(db, ks, "demo", 15, feeds, jobs)


def _unscored(db, targets):
    for i, t in enumerate(targets):
        db.execute("INSERT INTO forecasts(symbol, horizon, method, issued_t, target_t, price0, p_up, lo50, hi50, lo80, "
                   "hi80) VALUES('XAU', '15m', 'rw', ?, ?, 1, 0.5, 1, 1, 1, 1)", (t - 900 + i, t))


def test_judge_row_does_not_count_targets_of_a_short_day_or_holiday_as_overdue():
    # seen 2026-11-26 (Thanksgiving): the stream went quiet at 14:46 New York, the targets of the afternoon had no
    # candle, and the row said «111 overdue» although nothing was broken; the Judge drops them after a day
    db, ks, feeds, jobs, eng = _setup()
    _unscored(db, [1795723200 + 60 * i for i in range(60)])          # Thanksgiving 15:00-16:00 New York
    _unscored(db, [1798210800 + 60 * i for i in range(60)])          # Christmas Day 10:00-11:00 New York
    rows = {r["stage"]: r for r in pipeline.check(db, ks, eng, feeds, jobs, 1798246800.0)}   # 25.12 20:00 New York
    assert rows["Hakim (proqnozları yoxlayır)"]["n"] == 0
    assert rows["Hakim (proqnozları yoxlayır)"]["status"] == "ok"


def test_judge_row_still_counts_overdue_targets_of_an_ordinary_day():
    db, ks, feeds, jobs, eng = _setup()
    _unscored(db, [1795446000 + 60 * i for i in range(60)])          # Monday 23.11 10:00-11:00 New York
    rows = {r["stage"]: r for r in pipeline.check(db, ks, eng, feeds, jobs, 1795460400.0)}   # 14:00 New York
    assert rows["Hakim (proqnozları yoxlayır)"]["n"] == 60
    assert rows["Hakim (proqnozları yoxlayır)"]["status"] == "warn"


def test_price_row_on_a_short_day_afternoon_is_closed_not_bad():
    # Thanksgiving 16:30 New York: the US session has stopped early, 0/4 live is expected (the repair and the outside
    # watcher already know it), so the chain must not show the first link as broken
    db, ks, feeds, jobs, eng = _setup()
    rows = {r["stage"]: r for r in pipeline.check(db, ks, eng, feeds, jobs, 1795728600.0)}
    assert rows["Qiymət axını (4 metal)"]["status"] == "closed"
    assert "0/4" in rows["Qiymət axını (4 metal)"]["msg"]
