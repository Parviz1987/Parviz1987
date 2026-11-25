"""Bazarlar arası blok: each rule fires on its own condition, only from candles closed at that moment; the block's
replay writes rule_signals the Judge measures; the TA replay is not confused by the block's rows."""
import math

from app import candles, crossmarket as cm, rules
from app.db import DB
from app.engine import Engine
from app.keys import KeyStore


def _s(xs):
    return cm.Series(list(xs))


def _wiggle(n, base=100.0, amp=0.001, seed=1):
    out, x = [], base
    for i in range(n):
        x *= 1 + amp * math.sin(i * 1.7 + seed) * (1 if (i * seed) % 3 else -1)
        out.append(x)
    return out


def test_dollar_turn_and_fear_spike_and_pair_catch_up():
    n = 140
    metal = _wiggle(n, 100, 0.001, 2)
    dxy = _wiggle(n - 20, 100, 0.0005, 3)
    dxy += [dxy[-1] * (1 - 0.0012 * k) for k in range(1, 21)]          # the dollar starts falling steadily
    zs = [_s(dxy).mom_z(i) for i in range(101, n)]
    i = next(k for k in range(1, len(zs)) if zs[k - 1] > -cm.MOM_Z >= zs[k]) + 101
    out = cm.detect("XAU", i, {"_metal": _s(metal), "DXY": _s(dxy)})
    assert ("CM-USD-1", 1) in [(r, d) for r, d, _ in out]
    vix = _wiggle(n, 20, 0.002, 4)
    spx = _wiggle(n, 5000, 0.001, 5)
    vix[-1] = vix[-2] * 1.4
    spx[-1] = spx[-2] * 0.95
    out = cm.detect("XAU", n - 1, {"_metal": _s(metal), "VIX": _s(vix), "US500": _s(spx)})
    assert ("CM-RISK-1", 1) in [(r, d) for r, d, _ in out]
    pair = _wiggle(n, 40, 0.001, 6)
    pair[-1] = pair[-2] * 1.05
    metal[-1] = metal[-2]
    out = cm.detect("XAU", n - 1, {"_metal": _s(metal), "_pair": _s(pair)})
    assert ("CM-LEAD-1", 1) in [(r, d) for r, d, _ in out]
    # a missing candle of the other market: no rule from it
    gap = list(vix)
    gap[-50] = None
    assert not any(r == "CM-RISK-1" for r, _, _ in cm.detect("XAU", n - 1, {"_metal": _s(metal), "VIX": _s(gap), "US500": _s(spx)}))


def test_risk_on_rally_splits_gold_and_industrial_metals():
    n = 140
    spx = _wiggle(n - 25, 5000, 0.001, 7)
    spx += [spx[-1] * (1 + 0.004 * k) for k in range(1, 26)]
    vix = _wiggle(n - 25, 20, 0.002, 8) + [12.0] * 25
    zs = [_s(spx).mom_z(i) for i in range(101, n)]
    i = next(k for k in range(1, len(zs)) if zs[k - 1] < 2.0 <= zs[k]) + 101
    m = {"_metal": _s(_wiggle(n)), "VIX": _s(vix), "US500": _s(spx)}
    assert ("CM-RISK-2", -1) in [(r, d) for r, d, _ in cm.detect("XAU", i, m)]
    assert ("CM-RISK-2", 1) in [(r, d) for r, d, _ in cm.detect("XAG", i, m)]


def test_run_writes_measured_rows_and_ta_replay_is_not_confused():
    db = DB(":memory:")
    Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    rules.ensure(db)
    t0 = 1_700_000_000 // 3600 * 3600
    n = 400
    xau, xag = _wiggle(n, 2000, 0.002, 1), _wiggle(n, 25, 0.002, 2)
    xag[300] = xag[299] * 1.06
    xau[300] = xau[299]
    for code, xs in (("XAU", xau), ("XAG", xag)):
        candles.store_history(db, code, "1h", [(t0 + k * 3600, x, x * 1.001, x * 0.999, x) for k, x in enumerate(xs)])
    now = t0 + n * 3600 + 5
    assert cm.run(db, now) > 0
    rows = db.execute("SELECT * FROM rule_signals WHERE rule LIKE 'CM-%'").fetchall()
    assert rows and all(r["mode"] == "history" for r in rows)
    lead = [r for r in rows if r["rule"] == "CM-LEAD-1" and r["metal"] == "XAU"]
    assert lead and lead[0]["t"] == t0 + 300 * 3600 and lead[0]["price1"] is not None
    # a second run adds no copies for the same candles
    n1 = db.execute("SELECT COUNT(*) n FROM rule_signals").fetchone()["n"]
    cm.run(db, now)
    assert db.execute("SELECT COUNT(*) n FROM rule_signals").fetchone()["n"] == n1
    # the TA replay still sees no history of its own (CM rows must not count as «already replayed»)
    first = db.execute("SELECT 1 FROM rule_signals WHERE metal='XAU' AND tf='1h' AND mode='history' AND rule NOT LIKE "
                       "'CM-%' AND rule NOT LIKE 'TM-%' AND rule NOT LIKE 'HY-%' AND rule NOT LIKE 'FA-%' "
                       "AND rule NOT LIKE 'NW-%' LIMIT 1").fetchone()
    assert first is None
    v = cm.lookup(db).views("XAU", now, "1h")
    assert "bazarlar" in v
