"""Beyin keçidi: one action per error class, at most 4 calls per request, switched-off models stay off across calls
until the owner fixes the cause (a new key re-enables), overload trips a breaker, our own bad request is not retried
on another brain, a retired model becomes a proposal (never a silent swap), and parallel calls cannot pass the cap."""
import asyncio

import httpx

from app import brains, llm, llmrouter
from app.db import DB
from app.llm import LLMError


def run(chain, fn, db=None):
    db = db or DB(":memory:")

    async def no_sleep(*_):
        return None
    real = llmrouter.asyncio.sleep
    llmrouter.asyncio.sleep = no_sleep
    try:
        return db, asyncio.run(llmrouter.call(db, "reader", chain, fn))
    finally:
        llmrouter.asyncio.sleep = real


def test_classify():
    c = llmrouter.classify
    assert c(LLMError("x", 401))[0] == "key" and c(LLMError("x", 402))[0] == "balance"
    gem_minute = ('{"error": {"code": 429, "message": "You exceeded your current quota, please check your plan and billing '
                  'details.", "status": "RESOURCE_EXHAUSTED", "details": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel'
                  '-FreeTier"}, {"retryDelay": "36s"}]}}')
    assert c(LLMError("x", 429, 36.0, body=gem_minute)) == ("rate", 36.0)          # the per-minute limit is NOT billing
    assert c(LLMError("x", 429, body=gem_minute.replace("PerMinute", "PerDay")))[0] == "daily"
    assert c(LLMError("x", 429, body='{"error": {"type": "insufficient_quota"}}'))[0] == "billing"
    assert c(LLMError("x", 429, body="quota exceeded, limit: 0"))[0] == "billing"
    assert c(LLMError("x", 400, body="API key not valid. Please pass a valid API key."))[0] == "key"
    assert c(LLMError("x", 400, body="Your credit balance is too low"))[0] == "balance"
    assert c(LLMError("x", 429, 12.0))[0:2] == ("rate", 12.0)
    assert c(LLMError("x", 529))[0] == "overload" and c(LLMError("x", 400))[0] == "bad_request"
    assert c(LLMError("x", 404))[0] == "model" and c(LLMError("x", 200, hint="refusal"))[0] == "refusal"
    assert c(httpx.ConnectError("no"))[0] == "connect" and c(httpx.ReadTimeout("slow"))[0] == "timeout"


def test_billing_429_switches_off_without_retries_and_falls_back():
    calls = []

    async def fn(p, m, k):
        calls.append(p)
        if p == "gemini":
            raise LLMError("Gemini: HTTP 429", 429, body="RESOURCE_EXHAUSTED: billing is not enabled for this project")
        return {"ok": 1}
    db, (res, p, m, fb, err) = run([("gemini", "g", "k1"), ("openai", "o", "k2")], fn)
    assert res == {"ok": 1} and p == "openai" and fb and calls == ["gemini", "openai"]
    _, (res2, *_x) = run([("gemini", "g", "k1"), ("openai", "o", "k2")], fn, db)
    assert calls[2:] == ["openai"]                                # gemini stays off: no money spent on it
    v = llmrouter.view(db)
    assert any("ödəniş" in x["state"] for x in v["models"]) and v["slots_24h"]["reader"]["fallback_ok"] == 2


def test_new_key_re_enables_a_model_switched_off_for_its_key():
    async def bad(p, m, k):
        raise LLMError("açar", 401)

    async def good(p, m, k):
        return {"ok": 1}
    db, _ = run([("openai", "o", "old")], bad)
    _, (res, *_x) = run([("openai", "o", "old")], good, db)
    assert res is None                                           # same key: still off
    _, (res, *_x) = run([("openai", "o", "new")], good, db)
    assert res == {"ok": 1}


def test_overload_retries_once_then_breaker_opens_after_three():
    n = []

    async def fn(p, m, k):
        n.append(1)
        raise LLMError("busy", 529)
    db, (res, *_x) = run([("anthropic", "a", "k")], fn)
    assert res is None and len(n) == 2                           # one retry only
    run([("anthropic", "a", "k")], fn, db)
    assert len(n) == 3                                           # third error in 5 minutes: breaker open
    run([("anthropic", "a", "k")], fn, db)
    assert len(n) == 3                                           # no call while it cools down


def test_bad_request_is_not_repeated_on_another_brain_and_calls_are_capped():
    n = []

    async def bad(p, m, k):
        n.append(p)
        raise LLMError("bad", 400)
    _, (res, *_x) = run([("openai", "o", "k"), ("anthropic", "a", "k")], bad)
    assert res is None and n == ["openai", "anthropic"]          # not retried on the same model; the next may accept it
    m = []

    async def flaky(p, m_, k):
        m.append(p)
        raise httpx.ConnectError("down")
    run([("a", "1", "k"), ("b", "2", "k"), ("c", "3", "k")], flaky)
    assert len(m) <= llmrouter.MAX_CALLS


def test_retired_model_becomes_a_proposal():
    async def gone(p, m, k):
        e = LLMError("Gemini: HTTP 404", 404)
        e.suggested = "gemini-3-flash"
        raise e
    db, _ = run([("gemini", "gemini-2.5-flash", "k")], gone)
    pr = llmrouter.view(db)["proposals"]
    assert pr["gemini:gemini-2.5-flash"]["new"] == "gemini-3-flash"
    assert "sahibin" in pr["gemini:gemini-2.5-flash"]["status"]


def test_budget_is_reserved_before_calls_in_parallel():
    db = DB(":memory:")
    brains.save(db, "reader", {"provider": "openai", "model": "gpt-5.4-nano", "month_usd": 1})
    worst = brains._worst("unknown-model", "s" * 3000, "u" * 3000, 20000, False)
    assert worst > 0.3
    assert brains._reserve(db, "reader", 0.6) and not brains._reserve(db, "reader", 0.6)
    brains._release("reader", 0.6)
    assert brains._reserve(db, "reader", 0.6)
    brains._release("reader", 0.6)


def test_half_open_lets_exactly_one_test_call_and_a_failed_test_reopens_longer():
    db = DB(":memory:")
    rt = llmrouter.Router(db)
    now = 1_800_000_000.0
    for k in range(3):
        rt.failed("a", "m", "overload", None, "k", "busy", now=now + k)
    r = rt._row("a", "m")
    assert r["until"] > now and r["backoff"] == 600
    later = r["until"] + 1
    assert rt.usable("a", "m", "k", later)[0]                     # the one test call
    assert not rt.usable("a", "m", "k", later + 1)[0]             # others wait for it
    rt.failed("a", "m", "overload", None, "k", "busy", now=later + 2)
    r2 = rt._row("a", "m")
    assert r2["until"] == later + 2 + 600 and r2["backoff"] == 1200
    assert rt.usable("a", "m", "k", r2["until"] + 1)[0]
    rt.ok("a", "m")
    assert rt.usable("a", "m", "k", r2["until"] + 2)[0] and rt._row("a", "m")["until"] == 0


def test_billing_off_is_tested_again_after_six_hours_and_a_new_key_clears_it():
    db = DB(":memory:")
    rt = llmrouter.Router(db)
    rt.failed("gemini", "g", "billing", None, "k1", "no billing")
    assert not rt.usable("gemini", "g", "k1")[0]
    import time as _t
    assert rt.usable("gemini", "g", "k1", _t.time() + llmrouter.OFF_RETRY + 5)[0]
    rt2 = llmrouter.Router(db)
    rt2.reset("gemini", "g")
    rt2.failed("gemini", "g", "billing", None, "k1", "no billing")
    assert rt2.usable("gemini", "g", "k2")[0]                      # the owner saved a new (paid) key


def test_run_both_shares_one_budget_of_calls():
    import asyncio as aio
    from app.keys import KeyStore
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    ks.first = lambda p: "k"
    brains.save(db, "reporter", {"provider": "gemini", "model": "g", "fallback": "openai", "fallback_model": "o"})
    n = []

    async def search(provider, key, model, system, user, max_tokens=3000):
        n.append(provider)
        raise httpx.ConnectError("down")
    real = llm.search
    llm.search = search

    async def no_sleep(*_):
        return None
    rs = llmrouter.asyncio.sleep
    llmrouter.asyncio.sleep = no_sleep
    try:
        out = aio.run(brains.run_both(db, ks, "reporter", "s", "u"))
    finally:
        llm.search = real
        llmrouter.asyncio.sleep = rs
    assert all(d is None for d, _ in out) and len(n) <= llmrouter.MAX_CALLS


def test_a_timed_out_call_counts_its_worst_cost():
    import asyncio as aio
    from app.keys import KeyStore
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    ks.first = lambda p: "k"
    brains.save(db, "reader", {"provider": "openai", "model": "gpt-5.4-nano"})

    async def ask(*a, **k):
        raise httpx.ReadTimeout("slow")
    real = llm.ask
    llm.ask = ask
    try:
        aio.run(brains.run(db, ks, "reader", "s", "u", {"type": "object"}))
    finally:
        llm.ask = real
    assert brains.spent(db, "reader") > 0


def test_owner_approves_a_proposed_model_in_every_slot_that_used_the_old_one():
    db = DB(":memory:")
    brains.save(db, "reporter", {"provider": "gemini", "model": "gemini-2.5-flash", "fallback": "openai",
                                 "fallback_model": "gpt-5.4-nano"})
    rt = llmrouter.Router(db)
    rt.failed("gemini", "gemini-2.5-flash", "model", None, "k", "gone", "gemini-3-flash")
    out = llmrouter.decide(db, None, "approve", "gemini", "gemini-2.5-flash")
    assert "reporter" in out["note"] and brains.config(db, "reporter")["model"] == "gemini-3-flash"
    try:
        llmrouter.decide(db, None, "approve", "gemini", "nope")
        raise AssertionError
    except ValueError:
        pass
