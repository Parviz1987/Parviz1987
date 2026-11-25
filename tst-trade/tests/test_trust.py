from app import trust
from app.db import DB


def test_lights():
    assert trust.light(0.91, 22, 0.48)["light"] == "yellow"
    assert trust.light(0.54, 56, 0.67)["light"] == "red"
    assert trust.light(0.52, 100, 0.50)["light"] == "white"
    assert trust.light(0.9, 5, 0.5)["light"] == "wait"
    assert trust.light(0.5, 500, 0.5, proven=True)["light"] == "green"


def test_build_empty(tmp_path):
    d = trust.build(DB(str(tmp_path / "t.db")))
    assert "etibarlı" in d["head"] and isinstance(d["items"], list)


def test_one_way_market_brain_is_not_promising():
    """Owner 2026-11-25: a brain saying «down» 30 times out of 30 in a falling market (26 went down, 7 separate
    events) must not light yellow against a weak rival."""
    r = {"n": 30, "hit_rate": 0.87, "baseline_hit": 0.48, "trend_hit": 0.70, "said_up": 0, "went_up": 4, "events": 7}
    base = trust.brain_rival(r)
    assert abs(base - 26 / 30) < 1e-9
    assert trust.light(r["hit_rate"], r["n"], base, events=r["events"])["light"] == "white"
    assert trust.light(0.87, 30, 0.48)["light"] == "yellow"          # the old weak rival would have said yellow
