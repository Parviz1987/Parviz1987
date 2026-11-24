"""Block 6: debate (bull / bear / judge), liquidity, risk gate and decision."""
import asyncio

from app import brains, candles, risk
from app.brainjobs import BrainJobs
from app.brainviews import Lookup
from app.db import DB
from app.engine import Engine
from app.feeds import Feeds
from app.keys import KeyStore
from app.liquidity import Liquidity


def test_debate_bull_bear_then_judge(monkeypatch):
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    ks.set("openai", {"key": "sk-test-1234"})
    ks.set("anthropic", {"key": "sk-ant-test-1234"})
    jobs = BrainJobs(db, ks, Feeds(db, ks))
    seen = []

    async def fake(db_, keys, slot, system, user, schema, max_tokens=2000, search=False):
        seen.append((slot, system[:12]))
        if "judge a debate" in system:
            assert "dollar zəifdir" in user and "faiz qalxır" in user
            return {"metals": [{"symbol": "XAU", "p1h": 0.58, "p4h": 0.5, "p1d": 0.5, "why": "x"}]}, "rev"
        if "the BULL analyst" in system or "the BEAR analyst" in system:
            return {"metals": [{"symbol": "XAU", "case": "dollar zəifdir" if "BULL" in system else "faiz qalxır"}]}, "o"
        return {"summary": "s", "watch": [], "metals": []}, "t"
    monkeypatch.setattr(brains, "run", fake)
    now = 1_800_000_000
    assert asyncio.run(jobs.strategist(now))
    slots = [x[0] for x in seen]
    assert slots == ["strategist", "analyst2", "analyst2", "analyst2", "reviewer", "chartist"]
    assert Lookup(db).views("XAU", now + 600, "1h")["debate"][0] == 0.58


def test_liquidity_wide_spread_and_quiet_market():
    liq = Liquidity()
    t0 = 1_800_000_000 // 60 * 60
    for m in range(120):
        for _ in range(20):
            liq.add("XAU", t0 + m * 60, 100.0, 100.02)
    assert liq.view("XAU", t0 + 119 * 60)["state"] == "normal"
    liq.add("XAU", t0 + 125 * 60, 100.0, 100.10)                   # 5x wider, and 5 quiet minutes
    v = liq.view("XAU", t0 + 125 * 60)
    assert v["state"] == "nazik" and len(v["reasons"]) == 2


def test_gate_closed_when_price_not_live_and_decision_waits_without_proof():
    db = DB(":memory:")
    eng = Engine(db, KeyStore(db, "s" * 64), "capital", 15)
    g = risk.gate(db, eng, "XAU")
    assert not g["open"] and "canlı deyil" in g["reasons"][0]
    d = risk.decision(db, eng, "XAU")
    assert all(x["call"] == "GÖZLƏ" for x in d["desks"]) and "sübutu yoxdur" in d["desks"][0]["why"]


def test_hypotheses_count_only_forecasts_after_registration():
    from app import hypotheses
    from app.judge import insert
    db = DB(":memory:")
    Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    t_old, t_new = hypotheses.REGISTERED - 86400, hypotheses.REGISTERED + 3600
    rows = []
    for i, t in enumerate([t_old] * 50 + [t_new + j * 900 for j in range(10)]):
        rows.append(("XAU", "30m", "reversal", "live", t + i, t + i + 1800, 100.0, 0.6, 0, 0, 0, 0, "b"))
    insert(db, rows)
    db.execute("UPDATE forecasts SET price1=101.0")
    h8 = next(h for h in hypotheses.evaluate(db, hypotheses.REGISTERED + 86400) if h["id"] == "H8")
    assert h8["n"] == 10 and h8["hit_rate"] == 1.0 and h8["status"] == "az"     # the 50 old ones never count
