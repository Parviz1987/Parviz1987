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


def test_second_analyst_and_debate_run_every_four_hours_not_every_round():
    # plan 3.3 (owner 27.11): no edge in 383 and 93 views, 36 $ of the month's 89 $ — every 4 hours is enough
    from app.brainjobs import BrainJobs, SECOND_EVERY
    from app.db import DB
    from app.feeds import Feeds
    from app.keys import KeyStore
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    j = BrainJobs(db, ks, Feeds(db, ks))
    t = 1_795_442_400.0
    runs = [j._round_due("analyst2", t + k * 3600) for k in range(9)]
    assert runs == [True, False, False, False, True, False, False, False, True] and SECOND_EVERY == 4 * 3600
    assert j._round_due("debate", t)                    # each has its own clock
