"""Sınaq sürüşü: the fixed tasks are scored exactly; the owner's pre-approval rule lets a same-company replacement
in only when it is not worse and at most 20 % dearer; otherwise the proposal waits for the owner."""
import asyncio
import json

from app import braintrial as bt, brains, llm, llmrouter
from app.db import DB


def perfect():
    ans = [{"i": i, "value": v, "period": p, "direction": None} for i, (_, v, p) in enumerate(bt.TASKS)]
    ans += [{"i": len(bt.TASKS) + i, "value": None, "period": None, "direction": d} for i, (_, d) in enumerate(bt.LABELS)]
    return {"answers": ans}


def test_score():
    assert bt.score(perfect()) == 1.0 and bt.score(None) == 0.0
    half = perfect()
    for a in half["answers"][:10]:
        a["value"] = -1
    assert bt.score(half) == 0.5


def test_pre_approval_rule_applies_or_waits():
    db = DB(":memory:")
    brains.save(db, "reader", {"provider": "gemini", "model": "gemini-2.5-flash"})
    llmrouter.Router(db).failed("gemini", "gemini-2.5-flash", "model", None, "k", "gone", "gemini-3.8-flash")

    class K:
        def first(self, p):
            return "k"

    async def ask(provider, key, model, system, user, schema, max_tokens):
        return perfect(), 1000, 500
    real, prices = llm.ask, dict(llm.PRICES)
    llm.ask = ask
    llm.PRICES.update({"gemini-2.5-flash": (0.3, 2.5), "gemini-3.8-flash": (0.33, 2.7)})
    try:
        done = asyncio.run(bt.handle_proposals(db, K()))
    finally:
        llm.ask = real
        llm.PRICES.clear()
        llm.PRICES.update(prices)
    assert done and brains.config(db, "reader")["model"] == "gemini-3.8-flash"
    p = json.loads(db.get("llm:proposals"))["gemini:gemini-2.5-flash"]
    assert p["status"].startswith("qabaqcadan icazə") and p["trial"]["score"] == 1.0
    ok, why = bt.preapproved(db, "gemini", "a", "b", {"ok": True, "score": 1.0})
    assert not ok                                                     # unknown price: waits for the owner
