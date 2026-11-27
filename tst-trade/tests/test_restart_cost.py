import json
import time

from app.brainjobs import STRATEGIST_EVERY, BrainJobs
from app.db import DB
from app.feeds import Feeds
from app.keys import KeyStore


def _jobs(db):
    ks = KeyStore(db, "s" * 64)
    return BrainJobs(db, ks, Feeds(db, ks))


def test_a_restart_does_not_buy_an_extra_strategist_round():
    # seen 2026-11-27: every deploy restarted the server and the hourly strategist round (strategist, second analyst,
    # debate, chart reader: all paid) ran again at once; 12 restarts in one night cost the second analyst ~3 $ extra
    db = DB(":memory:")
    ran = time.time() - 600                    # the last round 10 minutes ago
    db.put("brainjob:strategist", json.dumps({"ts": ran, "message": "izah yazıldı"}))
    jobs = _jobs(db)
    assert abs(jobs.next_strategist - (ran + STRATEGIST_EVERY)) < 1


def test_the_first_start_still_runs_the_strategist_at_once():
    jobs = _jobs(DB(":memory:"))
    assert jobs.next_strategist <= time.time()
