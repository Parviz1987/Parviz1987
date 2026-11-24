"""Block 11: the learning scale (Hedge), calibration, and the nightly review with A/B lessons."""
import asyncio

from app import brains, learning
from app.brainjobs import BrainJobs
from app.db import DB
from app.engine import Engine
from app.feeds import Feeds
from app.judge import insert
from app.keys import KeyStore

NOW = 1_800_000_000


def test_hedge_rewards_recent_skill_and_keeps_a_floor():
    db = DB(":memory:")
    Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    rows = []
    for i in range(400):
        t = NOW - 86400 * 10 + i * 900
        rows.append(("XAU", "1h", "good", "history", t, t + 3600, 100.0, 0.6, 0, 0, 0, 0, "b"))
        rows.append(("XAU", "1h", "bad", "history", t, t + 3600, 100.0, 0.6, 0, 0, 0, 0, "b"))
    insert(db, rows)
    db.execute("UPDATE forecasts SET hit = CASE WHEN method='good' THEN (id % 10 < 7) ELSE (id % 10 < 3) END, "
               "outcome = (id % 2)")
    w = learning.hedge(db, "XAU", "1h", NOW)
    assert w["good"] > 1 > w["bad"] > 0                          # the bad one is light, never zero (floor)
    z_rows = [{"method": "good", "hit_rate": 0.7, "nh": 400, "bar": 0.5},
              {"method": "bad", "hit_rate": 0.3, "nh": 400, "bar": 0.5}]
    assert set(learning.combine(w, z_rows, 1)) == {"good"}


def test_calibration_moves_an_overconfident_brain_towards_reality():
    bands = {"strateq:1h": [[0.6, 1.01, 0.5, 80]]}                  # said 60-70 %, was right 50 % of 80 times
    p = learning.apply_calibration(bands, "strateq", "1h", 0.7)
    assert 0.5 < p < 0.6
    assert learning.apply_calibration(bands, "strateq", "4h", 0.7) == 0.7    # no data: unchanged


def test_nightly_review_writes_lessons_and_ab_days_alternate(monkeypatch):
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    jobs = BrainJobs(db, ks, Feeds(db, ks))
    monkeypatch.setattr(learning, "day_errors", lambda db_, now: [
        {"brain": "strateq", "metal": "XAU", "said_up_prob": 0.7, "reason": "dollar", "move_pct_next_hour": -0.4,
         "size": 0.1}] * 3)

    async def fake(db_, keys, slot, system, user, schema, max_tokens=2000, search=False):
        assert slot == "reviewer"
        return {"lessons": ["Dollar güclənəndə yuxarı meyli zəiflət."]}, "t"
    monkeypatch.setattr(brains, "run", fake)
    assert asyncio.run(jobs.sleep(NOW)) == 1
    assert learning.active_lessons(db, NOW) == ["Dollar güclənəndə yuxarı meyli zəiflət."]
    assert learning.lessons_today(db, NOW) != learning.lessons_today(db, NOW + 86400)


def test_old_default_brains_move_to_cheaper_defaults_but_keep_the_owner_limit():
    import json
    db = DB(":memory:")
    db.put("brain:strategist", json.dumps({"provider": "anthropic", "model": "claude-opus-5-5", "fallback": "gemini",
                                           "fallback_model": "gemini-4-argon", "month_usd": 35.0}))
    db.put("brain:reader", json.dumps({"provider": "xai", "model": "grok-x", "month_usd": 5.0}))   # owner's own
    eng = Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    eng.migrate()
    st = json.loads(db.get("brain:strategist"))
    assert st["model"] == "claude-sonnet-5-5" and st["month_usd"] == 35.0
    assert json.loads(db.get("brain:reader"))["model"] == "grok-x"


def test_cost_thermostat_slows_a_slot_heading_over_its_limit():
    from app import brains
    db = DB(":memory:")
    now = 1_800_000_000
    db.conn.executescript(brains.CALLS_SCHEMA)
    start = brains._month_start(now)
    db.execute("INSERT INTO brain_calls VALUES(?, 'strategist', 'anthropic', 'm', 1, 0, 0, 15.0, NULL)", (start + 3600,))
    assert brains.pace(db, "strategist", start + 3 * 86400) == 2.0     # 15 $ in 3 days -> far over 20 $
    assert brains.pace(db, "reader", start + 3 * 86400) == 1.0


def test_session_and_multispeed_trend_methods():
    from app import forecast
    assert forecast.seans_view(2 * 3600, "1h")[0] == 0.53          # 02:00 UTC: Asian hours
    assert forecast.seans_view(15 * 3600, "4h")[0] == 0.47         # 15:00 UTC: US hours
    assert forecast.seans_view(10 * 3600, "1h")[0] == 0.5          # London
    up = [{"o": 100 * 1.002 ** i, "h": 100 * 1.002 ** i, "l": 100 * 1.002 ** i, "c": 100 * 1.002 ** i * (1 + 0.003 * (-1) ** i)}
          for i in range(300)]
    p, why = forecast.trendmix_view(up, "1d")
    assert p > 0.5 and "yuxarı" in why
    assert {"seans"} <= set(forecast.methods_for("1h")) and "trendmix" in forecast.methods_for("1mo")
    assert "seans" not in forecast.methods_for("1d") and "trendmix" not in forecast.methods_for("1h")
