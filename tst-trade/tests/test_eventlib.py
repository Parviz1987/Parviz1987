"""Hadisələr kitabxanası: each release maps to the period it first published; the surprise uses only the past; the
moves start from the close before the event; analogs use only finished moves; the shadow test gates the brains."""
import json
import random
from datetime import datetime, timezone

from app import autojudge as aj, eventlib as el
from app.db import DB


def _ts(d):
    return datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()


def test_release_maps_to_the_period_it_first_published():
    obs_d = ["2023-12-01", "2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01", "2024-05-01"]
    obs_v = [99.8, 100.0, 100.3, 100.5, 100.9, 101.0]
    # CPI for April comes out mid May; a second release for the same period is not a new event
    rel = [_ts("2024-05-15"), _ts("2024-05-20")]
    out = el.releases_of("CPI", rel, obs_d, obs_v)
    assert len(out) == 1 and out[0]["period"] == "2024-04-01"
    assert abs(out[0]["change"] - (100.9 / 100.5 - 1) * 100) < 1e-9
    prev = [(100.0 / 99.8 - 1) * 100, (100.3 / 100.0 - 1) * 100, (100.5 / 100.3 - 1) * 100]
    assert abs(out[0]["base"] - sum(prev) / 3) < 1e-9


def test_surprise_uses_only_earlier_surprises():
    rows = [{"change": 1.0, "base": 0.0} for _ in range(10)] + [{"change": 5.0, "base": 0.0}]
    for i, r in enumerate(rows):
        r["change"] += 0.01 * (i % 3)
    el._zscore(rows)
    assert rows[0]["surprise"] is None and rows[-1]["surprise"] > 10
    assert el.category(1.0) == "yuxarı" and el.category(-1.0) == "aşağı" and el.category(0.1) == "yaxın"


def test_moves_start_before_the_event_day():
    ts = [_ts(f"2024-03-{d:02d}") for d in range(4, 16)]
    cs = [100.0 + i for i in range(len(ts))]
    ev = _ts("2024-03-06") + 13.5 * 3600
    m = el.moves(ts, cs, ev)
    assert abs(m["1d"][0] - (102 / 101 - 1)) < 1e-12 and abs(m["1w"][0] - (106 / 101 - 1)) < 1e-12


def test_analogs_only_see_finished_moves_and_the_shadow_test_gates_brains():
    db = DB(":memory:")
    el.ensure(db)
    random.seed(3)
    t0 = _ts("2015-01-01")
    lib, mv = [], []
    for i in range(400):
        t = t0 + i * 10 * 86400
        cat = "yuxarı" if i % 2 else "aşağı"
        lib.append((f"CPI:{i}", "CPI", t, None, None, None, None, None, cat, "trend əvəzi", 1, None))
        r = (-0.006 if cat == "yuxarı" else 0.006) + random.gauss(0, 0.004)   # a strong, real pattern
        for h in el.HORIZONS:
            mv.append((f"CPI:{i}", "XAU", h, r, t + 8 * 86400, 0))
    db.executemany("INSERT INTO ev_lib VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", lib)
    db.executemany("INSERT INTO ev_move VALUES(?,?,?,?,?,?)", mv)
    evs, m = el._events(db), el._moves_of(db, "XAU", "1d")
    assert el.analogs(evs, m, "CPI", "yuxarı", 1, t0 + 5 * 86400) == []          # nothing finished yet
    res = el.shadow_test(db)
    assert "XAU:1d" in res["passed"] and "XAG:1d" not in res["passed"]
    lines = el.for_brains(db, [{"title": "CPI m/m"}], [])
    assert lines and all(x["metal"] == "XAU" for x in lines)
    assert {x["outcome_vs_expected"] for x in lines} == {"yuxarı", "aşağı"}
    up = [x for x in lines if x["outcome_vs_expected"] == "yuxarı" and x["horizon"] == "1d"][0]
    assert up["up_share"] < 0.2
    db.put(el.KEY_TEST, json.dumps({"passed": []}))
    assert el.for_brains(db, [{"title": "CPI m/m"}], []) == []                    # no proof: the brains get nothing


def test_middle_way_shadow_only():
    assert aj.early_shadow(aj.OFF, 75, None, False)
    assert aj.early_shadow(aj.OFF, 75, 0.2, False)
    assert not aj.early_shadow(aj.OFF, 75, -1.5, False)        # live already points the wrong way
    assert not aj.early_shadow(aj.OFF, 60, None, False)        # history not strong enough
    assert not aj.early_shadow(aj.OFF, 90, None, True)         # a veto holds
    assert not aj.early_shadow(aj.SMALL, 90, 3.0, False)       # never moves a stage down or past shadow
    assert aj.size_factor(aj.SHADOW, 90, 1.0) == 0.0           # shadow never trades


def test_fomc_decision_from_the_target_rate():
    db = DB(":memory:")
    db.script("CREATE TABLE IF NOT EXISTS macro_first (series TEXT NOT NULL, d TEXT NOT NULL, v REAL NOT NULL, "
              "PRIMARY KEY (series, d));")
    days = [f"2024-09-{d:02d}" for d in range(10, 25)]
    db.executemany("INSERT INTO macro_first VALUES('DFEDTARU',?,?)",
                   [(d, 5.5 if d < "2024-09-19" else 5.0) for d in days])
    hold, cut = _ts("2024-09-12") + 18 * 3600, _ts("2024-09-18") + 18 * 3600
    ev = {e["t"]: e for e in el.fomc_events(db, [hold, cut])}
    assert ev[cut]["cat"] == "aşağı" and ev[cut]["change"] == -50 and ev[hold]["cat"] == "yaxın"


def test_gdelt_parse_averages_per_day():
    data = {"timeline": [{"series": "Volume Intensity", "data": [
        {"date": "20240101T000000Z", "value": 1.0}, {"date": "20240101T120000Z", "value": 3.0},
        {"date": "20240102T000000Z", "value": 0.5}, {"date": "bad", "value": "x"}]}]}
    assert el.parse_gdelt(json.dumps(data)) == {"2024-01-01": 2.0, "2024-01-02": 0.5}
    try:
        el.parse_gdelt("{}")
        raise AssertionError("must fail")
    except ValueError:
        pass


def test_geo_jump_is_against_the_past_and_known_after_the_day():
    days = [datetime.fromtimestamp(_ts("2024-01-01") + i * 86400, timezone.utc).strftime("%Y-%m-%d")
            for i in range(130)]
    vals = [1.0] * 130
    vals[100], vals[103], vals[120] = 2.5, 1.8, 1.6       # a big jump, one inside the 7-day gap, a medium one
    evs = el.geo_events((days, vals), _ts("2025-01-01"))
    assert [(e["period"], e["cat"]) for e in evs] == [(days[100], "böyük"), (days[120], "orta")]
    assert evs[0]["t"] == _ts(days[100]) + 86400               # knowable only when the day is over
    assert el.geo_events((days, vals), _ts(days[100]) + 3600) == []
    db = DB(":memory:")
    el.ensure(db)
    db.executemany("INSERT INTO geo_vol VALUES(?,?)", list(zip(days, vals)))
    assert el.geo_now(db, _ts(days[120]) + 86400 + 3600)[0] == "orta"
    assert el.geo_now(db, _ts(days[125]) + 86400 + 3600) is None
