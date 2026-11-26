"""Kölgə sınaqları: the fundamental vote with a 3-year record window is scored next to the live whole-record vote on
the same days; a rule whose old record was good but recent record is bad loses its weight only in the window; the
festival test finds higher volatility before festivals when it is there, and says «not proven» when it is not."""
import math
import random

from app import rules, shadowtests
from app.db import DB

DAY = 86400


def test_window_drops_a_rule_whose_recent_record_turned_bad():
    db = DB(":memory:")
    rules.ensure(db)
    t0 = 1_500_000_000 // DAY * DAY
    rows = []
    for i in range(2400):                       # ~6.5 years of daily firings: right for 4 years, then wrong
        t = t0 + i * DAY
        right = i < 1500
        rows.append(("XAU", "1d", t, "FA-RY-1", 1, 100.0, 101.0 if right else 99.0))
    db.executemany("INSERT INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode) VALUES(?,?,?,?,?,?,?,'history')", rows)
    from app import fundamental
    whole = rules.Lookup(db, prefixes=("FA-",), name="fundamental", tfs=("1d",), families=fundamental.FAMILY)
    win = rules.Lookup(db, prefixes=("FA-",), name="fundamental", tfs=("1d",), families=fundamental.FAMILY,
                       window=shadowtests.YEARS3)
    t = t0 + 2390 * DAY
    assert whole.weight("FA-RY-1", "1d", t)[0] > 0
    assert win.weight("FA-RY-1", "1d", t)[0] == 0
    out = shadowtests.fa_window(db, symbols=("XAU",))["XAU"]
    assert out["bütün keçmiş"]["n"] == out["son 3 il"]["n"] > 2000
    assert out["3il_minus_hamisi_brier"]["mean"] < 0           # the window forecast the turned rule better


def test_festival_volatility_found_and_not_invented():
    from app.slowviews import DIWALI
    from datetime import date, datetime, timedelta, timezone
    random.seed(4)
    db = DB(":memory:")
    fest = set()
    for d in DIWALI:
        f = date.fromisoformat(d)
        fest.update(f - timedelta(days=k) for k in range(1, 22))
    d0 = date(2015, 1, 5)
    for loud in (True, False):
        db.execute("DELETE FROM candles")
        c, rows = 1000.0, []
        for i in range(3600):
            d = d0 + timedelta(days=i)
            if d.weekday() >= 5:
                continue
            vol = 0.02 if (loud and d in fest) else 0.008
            c *= math.exp(random.gauss(0, vol))
            t = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()) - 7200
            rows.append(("XAU", "1d", t, c, c, c, c))
        db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'history')", rows)
        r = shadowtests.festival_vol(db, symbols=("XAU",))["XAU"]
        if loud:
            assert r["t"] > 2 and r["ratio"] > 1.5 and "yüksəkdir" in r["verdict"]
        else:
            assert "sübut olunmayıb" in r["verdict"]


def test_unfamiliar_and_lead_lag_run_and_find_a_planted_lead():
    db = DB(":memory:")
    random.seed(8)
    t0 = 1_600_000_000 // 3600 * 3600
    g, m, rows = 1800.0, 100.0, []
    prev_m = 0.0
    for i in range(2000):
        dm = random.gauss(0, 0.002)
        g *= math.exp(0.6 * prev_m + random.gauss(0, 0.001))       # gold follows the dollar index one hour later
        m *= math.exp(dm)
        prev_m = dm
        rows.append(("XAU", "1h", t0 + i * 3600, g, g, g, g))
        rows.append(("DXY", "1h", t0 + i * 3600, m, m, m, m))
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'history')", rows)
    out = shadowtests.lead_lag(db)
    assert out["DXY"]["lead_t"] > 3 and "əvvəl" in out["DXY"]["verdict"]
    assert "note" in shadowtests.unfamiliar(db)                       # no daily candles here: says so, no crash
