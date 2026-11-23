import asyncio

from app import brainjobs, brains, llm
from app.db import DB
from app.feeds import Feeds
from app.keys import KeyStore

S = "s" * 64


def setup():
    db = DB(":memory:")
    ks = KeyStore(db, S)
    return db, ks, brainjobs.BrainJobs(db, ks, Feeds(db, ks))


def test_guard_numbers_drops_invented_numbers():
    facts = '{"price": 3608.0, "range80": [3590.5, 3620.25]}'
    text = "Qızıl 3608 səviyyəsindədir. Sabah 3700 olacaq. Aralıq 3590.5 ilə 3620.25 arasıdır."
    out = brainjobs.guard_numbers(text, facts)
    assert "3700" not in out and "3608" in out and "3620.25" in out


def test_reader_labels_only_given_headlines(monkeypatch):
    db, ks, jobs = setup()
    ks.set("openai", {"key": "sk-test-1234"})
    db.execute("INSERT INTO news(uid, source, url, title, ts, metals) VALUES('n1','s','','Fed hikes',?,'')",
               (1000.0,))

    async def fake_ask(provider, key, model, system, user, schema, max_tokens=2000):
        assert provider == "openai" and "n1: Fed hikes" in user
        return {"items": [{"id": "n1", "metals": ["XAU"], "direction": "down", "strength": 2, "event": "fed"},
                          {"id": "ghost", "metals": ["XAG"], "direction": "up", "strength": 3, "event": "x"}]}, 100, 20
    monkeypatch.setattr(llm, "ask", fake_ask)
    n = asyncio.run(jobs.reader(1000.0 + 60))
    assert n == 1
    row = db.execute("SELECT * FROM news_ai").fetchone()
    assert row["uid"] == "n1" and row["direction"] == "down" and row["strength"] == 2
    assert brains.spent(db, "reader", 1060.0) > 0


def test_fallback_and_cap(monkeypatch):
    db, ks, jobs = setup()
    ks.set("anthropic", {"key": "sk-ant-1234"})
    ks.set("gemini", {"key": "g-1234"})
    calls = []

    async def fake_ask(provider, key, model, system, user, schema, max_tokens=2000):
        calls.append(provider)
        if provider == "anthropic":
            raise llm.LLMError("Anthropic: HTTP 529")
        return {"summary": "ok", "metals": [], "watch": []}, 10, 10
    monkeypatch.setattr(llm, "ask", fake_ask)
    assert asyncio.run(jobs.strategist(1795400000.0))
    assert calls == ["anthropic", "gemini"]
    assert jobs.last_explanation()["brain"].startswith("gemini")
    brains.save(db, "strategist", {"month_usd": 0})
    data, why = asyncio.run(brains.run(db, ks, "strategist", "s", "u", {}))
    assert data is None and "limit" in why


def test_no_key_never_raises():
    db, ks, jobs = setup()
    data, why = asyncio.run(brains.run(db, ks, "reader", "s", "u", {}))
    assert data is None and "açar yoxdur" in why
