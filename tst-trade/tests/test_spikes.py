"""Plan 27.11 step 8.1: a one-minute spike is seen within a minute (the 15-minute check waits for the quarter)."""
import random

from app import signals
from app.db import DB

NOW = 1_795_442_400.0 + 30                       # Monday 10:00:30 New York: the 10:00 minute is still open


def _minutes(db, jump=0.0):
    random.seed(5)
    c, rows = 4000.0, []
    t0 = int(NOW // 60) * 60 - 300 * 60
    for i in range(300):
        c *= 1 + random.gauss(0, 0.0002) + (jump if i == 299 else 0)
        rows.append(("XAU", "1m", t0 + i * 60, c, c, c, c))
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'live')", rows)


def test_a_one_minute_spike_raises_a_move_alarm():
    db = DB(":memory:")
    signals.ensure(db)
    _minutes(db, jump=0.004)                     # +0.4 % in the last closed minute
    assert signals.from_spikes(db, NOW, ["XAU"]) == 1
    s = signals.recent(db)[0]
    assert s["kind"] == "move" and "1 dəqiqədə" in s["text"] and s["strength"] == 3
    assert signals.from_spikes(db, NOW, ["XAU"]) == 0          # the same minute never alarms twice


def test_an_ordinary_minute_raises_nothing():
    db = DB(":memory:")
    signals.ensure(db)
    _minutes(db)
    assert signals.from_spikes(db, NOW, ["XAU"]) == 0
