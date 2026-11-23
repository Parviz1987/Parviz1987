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
