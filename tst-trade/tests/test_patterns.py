"""All 12 kinds of technical analysis (owner 2026-11-25): detectors, the stop + target test, tick volume, replay."""
import re
from pathlib import Path

from app import candles, patterns, playbook, rules
from app.db import DB


def _c(t, o, h, l, c, v=None):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


def _series(closes, v=None):
    out, prev = [], closes[0]
    for k, x in enumerate(closes):
        o = prev
        out.append(_c(1_700_000_000 + 3600 * k, o, max(o, x) + 0.3, min(o, x) - 0.3, x, v))
        prev = x
    return out


def test_every_detector_rule_in_the_book_is_detected_in_code():
    code = Path(rules.__file__).read_text() + Path(patterns.__file__).read_text()
    found = set(re.findall(r'"((?:TA|TH|PA|VOL|IM)-[A-Z0-9-]+)"', code))
    for r in playbook.RULES:
        if r["detector"]:
            assert r["id"] in found, r["id"]
    for rid in found:
        assert rid in playbook.BY_ID, rid                     # nothing detected that the book does not explain


def test_zigzag_alternates_and_keeps_the_extreme():
    cs = _series([10, 12, 11, 13, 9, 14, 8])
    zz = patterns.zigzag(cs, [1, 3, 5], [2, 4, 6])
    kinds = [k for _, k, _ in zz]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))
    zz2 = patterns.zigzag(cs, [1, 3], [])                      # two highs in a row: the higher one stays
    assert len(zz2) == 1 and zz2[0][0] == 3


def test_stop_target_counts_the_stop_first_and_waits_for_20_candles():
    flat = [_c(k, 100, 100.2, 99.8, 100) for k in range(30)]
    flat[3] = _c(3, 100, 103, 98, 100)                         # touches both: the stop counts (cautious)
    assert rules.stop_target(flat, 0, 1, 1.0) == (-1.0, 3)
    up = [_c(k, 100 + k, 100 + k + 0.5, 100 + k - 0.5, 100 + k) for k in range(30)]
    assert rules.stop_target(up, 0, 1, 1.0) == (2.0, 2)
    assert rules.stop_target(up, 15, 1, 1.0) is None          # 20 candles have not closed yet


def test_stochastic_and_obv():
    cs = _series([100 - k * 0.5 for k in range(20)] + [95, 96, 97, 98], v=10)
    k, d = patterns.stochastic(cs)
    assert k[19] is not None and k[19] < 20 and k[-1] > k[19]
    o = patterns.obv(cs)
    assert o[19] < 0 and o[-1] > o[19]
    assert patterns.obv(_series([1, 2, 3]))[2] is None         # no volume: no OBV


def test_double_top_fires_when_the_neckline_breaks():
    xs = [100 + k * 0.05 for k in range(230)]                  # long quiet rise for the indicators
    base = xs[-1]
    up = [base + 1.5 * k for k in range(1, 7)]                 # to the first top
    down = [up[-1] - 1.5 * k for k in range(1, 6)]             # to the neckline
    up2 = [down[-1] + 1.5 * k for k in range(1, 6)]            # the second, equal top
    fall = [up2[-1] - 1.5 * k for k in range(1, 12)]           # through the neckline
    cs = _series(xs + up + down + up2 + fall)
    ind = rules.Ind(cs)
    fired = []
    for i in range(240, len(cs)):
        fired += [r for r, d, _ in rules.detect(ind, i, tf="1h") if r == "TA-PAT-1" and d == -1]
    assert fired


def test_tick_volume_counts_price_changes_only():
    db = DB(":memory:")
    for p in (10.0, 10.0, 10.1, 10.1, 10.2):
        candles.add_tick(db, "XAU", 1_800_000_000, p)
    row = candles.get(db, "XAU", "1h")[-1]
    assert row["v"] == 3                                       # first tick + two changes
    candles.store_history(db, "XAG", "1h", [(1_800_000_000 // 3600 * 3600, 1, 1, 1, 1)])
    candles.add_tick(db, "XAG", 1_800_000_000, 2.0)            # a history candle finished live: never part-counted
    assert candles.get(db, "XAG", "1h")[-1]["v"] is None


def test_new_detector_version_replays_old_history_once(monkeypatch):
    db = DB(":memory:")
    rules.ensure(db)
    db.execute("INSERT INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note) "
               "VALUES('XAU','1h',1,'TA-TREND-1',1,1,1,'history','x')")
    db.put("rules:ver:XAU:1h", "old")
    seen = {}
    real = rules.detect

    def spy(ind, i, higher=None, pair=None, tf="1h"):
        seen.setdefault(tf, []).append(i)
        return real(ind, i, higher, pair, tf)
    monkeypatch.setattr(rules, "detect", spy)
    cs = _series([100 + (k % 50) * 0.3 for k in range(400)])
    monkeypatch.setattr(rules, "_load", lambda db_, sym, tf, now, limit=4500: cs if sym == "XAU" and tf == "1h" else [])
    rules.run(db, now=2_000_000_000)
    assert min(seen["1h"]) == 210                              # replayed from the start
    assert db.get("rules:ver:XAU:1h") == rules.RULES_VER
    seen.clear()
    rules.run(db, now=2_000_000_000)
    assert min(seen.get("1h", [10 ** 9])) >= 370               # then only the newest candles
    rec = rules.records(db)
    assert "rules" in rec


def test_volume_rules_are_tested_once_on_futures_volume():
    import random
    from app import futures
    db = DB(":memory:")
    db.script(futures.SCHEMA)
    random.seed(3)
    x, rows = 3000.0, []
    for k in range(60 * 24 * 40):                         # 40 days of one-minute bars with real volume
        o = x
        x *= 1 + random.gauss(0, 0.0006)
        rows.append(("XAU", 1_790_000_040 + 60 * k, o, max(o, x), min(o, x), x, random.randint(1, 50) *
                     (20 if k % 997 == 0 else 1)))
    db.executemany("INSERT INTO fut_candles(symbol, t, o, h, l, c, v) VALUES(?,?,?,?,?,?,?)", rows)
    n = rules.run_futures_volume(db)
    got = db.execute("SELECT DISTINCT rule, mode FROM rule_signals").fetchall()
    assert n > 0 and all(r["rule"].startswith("VOL-") and r["mode"] == "futures" for r in got)
    assert rules.run_futures_volume(db) == 0               # once
    assert "VOL-" in "".join(rules.records(db)["rules"])
