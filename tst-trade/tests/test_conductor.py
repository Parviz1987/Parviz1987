"""Dirijor, part 1 (the evidence): each forecast moment gets the market state known at that moment, and per voice and
state the hit rate, its edge over that state's bar and the separate trading days are counted; a voice that is right only
in trends shows it, and the test on trading days says its hit rate differs between states."""
import math
import random

from app import conductor
from app.db import DB

DAY = 86400
T0 = 1_600_000_000 // DAY * DAY


def _candles(db, closes):
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES('XAU','1d',?,?,?,?,?,'history')",
                   [(T0 + i * DAY, c, c, c, c) for i, c in enumerate(closes)])


def _fc(db, method, t, p, outcome):
    hit = int((p > 0.5) == bool(outcome))
    db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, lo80, "
               "hi80, basis, price1, outcome, hit) VALUES('XAU','1d',?,'history',?,?,1,?,1,1,1,1,'',1,?,?)",
               (method, t, t + DAY, p, outcome, hit))


def test_states_follow_volatility_and_trend(monkeypatch):
    random.seed(1)
    closes, c = [], 1000.0
    for i in range(700):
        drift = 0.004 if 400 <= i < 460 else 0.0          # a clear uptrend
        vol = 0.03 if 550 <= i < 600 else 0.005           # a volatile spell
        c *= math.exp(drift + random.gauss(0, vol))
        closes.append(c)
    d = conductor.Daily([{"t": T0 + i * DAY, "c": x} for i, x in enumerate(closes)])
    ev = conductor.Events.__new__(conductor.Events)
    ev.ts, ev.covered_from = [], 1e18                     # no calendar: never an event (covered from far future)
    ev.inside = lambda a, b: False
    at = lambda i: conductor.state(d, ev, T0 + (i + 1) * DAY + 3600, T0 + (i + 2) * DAY)
    shock = [at(i) for i in range(570, 600)]
    assert shock.count("şok") > len(shock) * 0.8
    assert at(300) in ("yan", "trend", "şok")
    monkeypatch.setattr(conductor, "SHOCK_PCT", 1.01)     # a flat-volatility test series: look at the trend alone
    trend = [at(i) for i in range(430, 460)]
    assert trend.count("trend") > len(trend) * 0.8
    assert [at(i) for i in range(330, 360)].count("yan") > 15
    assert conductor.state(d, ev, T0 + 10 * DAY, T0 + 11 * DAY) is None      # not a year of history yet


def test_payroll_friday_is_an_event():
    # Friday 2026-11-06 08:30 New York is the first Friday of November
    from datetime import datetime
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    t = datetime(2026, 11, 6, 8, 30, tzinfo=ny).timestamp()
    assert conductor._payroll_inside(t - 3600, t + 60)
    assert not conductor._payroll_inside(t + 60, t + 7200)


def test_a_voice_right_only_in_trends_is_seen():
    random.seed(2)
    db = DB(":memory:")
    closes, c = [], 1000.0
    trend_days = set()
    for i in range(900):
        up = (i // 60) % 3 == 0                            # trend spells of 60 days, then quiet
        c *= math.exp((0.004 if up else 0.0) + random.gauss(0, 0.005))
        closes.append(c)
    _candles(db, closes)
    d = conductor.Daily([{"t": T0 + i * DAY, "c": x} for i, x in enumerate(closes)])
    ev = conductor.Events(db)
    for i in range(300, 899):
        t = T0 + (i + 1) * DAY + 3600
        s = conductor.state(d, ev, t, t + DAY)
        outcome = int(closes[i + 1] > closes[i]) if i + 1 < len(closes) else 1
        right = random.random() < (0.75 if s == "trend" else 0.5)
        p = 0.6 if (outcome == 1) == right else 0.4
        _fc(db, "tsmom", t, p, outcome)
        _fc(db, "rw", t, 0.6, outcome)                     # a baseline: left out
    out = conductor.audit(db, symbols=("XAU",))
    desk = out["desks"]["XAU:1d"]
    assert "rw" not in desk["voices"]
    st = desk["voices"]["tsmom"]["states"]
    assert st["trend"]["hit_rate"] > 0.65 and st["yan"]["hit_rate"] < 0.6
    assert desk["voices"]["tsmom"]["p_same"] is not None and desk["voices"]["tsmom"]["p_same"] < 0.05
    v = conductor.audit_view(db)
    assert any(x["voice"] == "tsmom" for x in v["desks"]["XAU:1d"]["differ"])
    assert not conductor.audit_due(db)


def test_chi2_tail():
    assert abs(conductor._chi2_sf(3.841, 1) - 0.05) < 0.002
    assert abs(conductor._chi2_sf(7.815, 3) - 0.05) < 0.002
