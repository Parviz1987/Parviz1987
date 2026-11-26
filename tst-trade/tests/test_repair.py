"""Avtomatik təmir: only catalogue steps, never while the owner's switch is pressed, within limits; the price falls
back to gold-api.com after 3 silent minutes x 3 checks in open hours and returns after 30 minutes; the same fault
twice in 7 days opens a review, a third time waits for the owner."""
import datetime as dt

from app import ops, repair
from app.db import DB


class Stop:
    def is_set(self):
        return False


class Eng:
    def __init__(self):
        self.fallback_until, self.last_ok, self.resets = 0.0, None, 0
        self._task, self._stop = None, Stop()

    def chosen_provider(self):
        return "goldapi" if self.fallback_until else "capital"

    def reset_provider(self):
        self.resets += 1


TUE = dt.datetime(2026, 11, 24, 15, tzinfo=dt.timezone.utc).timestamp()


def test_price_fallback_after_three_silent_checks_and_back_after_30_minutes():
    db, e = DB(":memory:"), Eng()
    r = repair.Repairer(db, e)
    r.started = TUE - 3600
    e.last_ok = TUE - 400
    assert r.check(TUE) == [] and r.check(TUE + 60) == []
    assert r.check(TUE + 120) == ["price_fallback: gold-api.com 30 dəqiqə"]
    assert e.fallback_until == TUE + 120 + repair.FALLBACK_FOR and e.resets == 1
    assert r.check(TUE + 200) == []
    assert "qayıtdı" in r.check(e.fallback_until + 1)[0] and e.fallback_until == 0.0


def test_nothing_while_paused_or_closed_and_limits_hold():
    db, e = DB(":memory:"), Eng()
    r = repair.Repairer(db, e)
    r.started = TUE - 3600
    e.last_ok = TUE - 400
    ops.set_paused(db, True)
    for k in range(5):
        r.check(TUE + k * 60)
    assert e.fallback_until == 0.0
    ops.set_paused(db, False)
    sat = dt.datetime(2026, 11, 28, 15, tzinfo=dt.timezone.utc).timestamp()
    for k in range(5):
        r.check(sat + k * 60)
    assert e.fallback_until == 0.0                               # market closed: silence is normal
    assert repair.allowed(db, "price_fallback", "x", TUE)[0]
    repair.record(db, "price_fallback", "x", "", "", TUE)
    assert not repair.allowed(db, "price_fallback", "y", TUE + 60)[0]   # 1 per 30 minutes


def test_repeat_opens_a_review_and_the_third_time_waits_for_the_owner():
    db = DB(":memory:")
    repair.record(db, "wal_checkpoint", "db:wal_big", "", "", TUE)
    assert repair.view(db)["open_reviews"] == 0
    repair.record(db, "wal_checkpoint", "db:wal_big", "", "", TUE + 7200)
    assert repair.view(db)["open_reviews"] == 1
    ok, why = repair.allowed(db, "wal_checkpoint", "db:wal_big", TUE + 3 * 7200)
    assert not ok and "sahibin" in why
    rid = repair.view(db)["reviews"][0]["id"]
    repair.close_review(db, rid, "düzəldildi: disk böyüdüldü")
    assert repair.view(db)["open_reviews"] == 0
