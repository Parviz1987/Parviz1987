"""Vaxt və təqvim bloku: US holidays by the NYSE rules, each calendar rule on its own day or hour, the voice computed
for the very candle being forecast, the replay measured like every rule."""
from datetime import date, datetime, timezone

from app import candles, rules, timeblock as tb
from app.db import DB
from app.engine import Engine
from app.keys import KeyStore


def _ts(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=timezone.utc).timestamp()


def test_us_holidays():
    h = tb.us_holidays(2026)
    assert date(2026, 11, 26) in h and date(2026, 4, 3) in h and date(2026, 7, 3) in h      # Thanksgiving, Good Friday, July 4 observed
    assert date(2026, 6, 19) in h and len(h) == 10
    assert date(2021, 6, 18) not in tb.us_holidays(2021)


def test_calendar_rules_fire_on_their_days_and_hours():
    names = lambda tf, t: {r for r, _, _ in tb.detect(tf, [{"t": t, "o": 1, "c": 1}], 0, None)}
    # 1h candle 01:00 UTC -> next hour 02:00 UTC: Asian hours
    assert "TM-SES-1" in names("1h", _ts(2026, 11, 24, 1))
    assert "TM-SES-2" in names("1h", _ts(2026, 11, 24, 15))
    # London 15:00 in winter = 15:00 UTC: candle 14:00 UTC is followed by the fix hour
    assert "TM-FIX-1" in names("1h", _ts(2026, 11, 24, 14))
    # daily candle labelled D starts 22:00 UTC the evening before: Monday 2026-11-30 starts Sun 22:00
    assert "TM-DOW-1" in names("1d", _ts(2026, 11, 28, 22))            # the candle before starts Sat 22:00
    assert "TM-HOL-1" in names("1d", _ts(2026, 11, 23, 22))            # next day Wed 25th, Thanksgiving on 26th
    assert "TM-TOM-1" in names("1d", _ts(2026, 11, 29, 22))            # next day Mon 30th: the last trading day
    assert "TM-TOM-1" in names("1d", _ts(2026, 11, 30, 22))            # next day Tue Dec 1st: the first


def test_data_hour_continuation_needs_a_big_candle():
    t = _ts(2026, 11, 24, 13)                        # 08:00-09:00 New York (EST): covers 08:30
    cs = [{"t": t, "o": 100.0, "c": 101.0}]
    assert ("TM-DATA-1", 1) in [(r, d) for r, d, _ in tb.detect("1h", cs, 0, 0.2)]
    assert "TM-DATA-1" not in [r for r, _, _ in tb.detect("1h", cs, 0, 0.8)]


def test_run_and_voice():
    db = DB(":memory:")
    Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    rules.ensure(db)
    t0 = int(_ts(2026, 10, 1))
    candles.store_history(db, "XAU", "1h", [(t0 + k * 3600, 100, 100.2, 99.8, 100 + (k % 3) * 0.1) for k in range(600)])
    now = t0 + 600 * 3600 + 5
    assert tb.run(db, now) > 0
    n1 = db.execute("SELECT COUNT(*) n FROM rule_signals").fetchone()["n"]
    tb.run(db, now)                                   # the last candle is looked at again (one candle of grace): no copies
    assert db.execute("SELECT COUNT(*) n FROM rule_signals").fetchone()["n"] == n1
    rows = db.execute("SELECT rule, COUNT(*) n FROM rule_signals WHERE rule LIKE 'TM-%' GROUP BY rule").fetchall()
    assert {r["rule"] for r in rows} >= {"TM-SES-1", "TM-SES-2", "TM-FIX-1"}
    v = tb.lookup(db).views("XAU", now, "1h")
    assert "vaxt" in v
