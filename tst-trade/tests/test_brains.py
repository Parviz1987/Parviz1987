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


def test_reader_score_checks_direction_one_hour_later():
    from app import candles
    from app.brainjobs import BrainJobs, reader_score
    from app.db import DB
    from app.feeds import Feeds
    from app.keys import KeyStore
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    BrainJobs(db, ks, Feeds(db, ks))
    t0 = 1_700_000_000 // 60 * 60
    for i in range(0, 130):
        candles.add_tick(db, "XAU", t0 + i * 60 + 1, 100 + i * 0.1)      # steady rise
    db.execute("INSERT INTO news_ai VALUES('a', ?, 'cpi', 'XAU', 'up', 2, 'x')", (t0 + 120,))
    db.execute("INSERT INTO news_ai VALUES('b', ?, 'cpi', 'XAU', 'down', 1, 'x')", (t0 + 180,))
    db.execute("INSERT INTO news_ai VALUES('c', ?, 'cpi', 'XAU', 'neutral', 0, 'x')", (t0 + 180,))
    rs = reader_score(db, t0 + 130 * 60 + 200)
    assert rs["n"] == 2 and rs["hit_rate"] == 0.5
    assert {r["strength"]: r["hit_rate"] for r in rs["rows"]} == {1: 0.0, 2: 1.0}


def test_scout_search_parses_responses_output_and_strips_numbers(monkeypatch):
    import asyncio
    import json as _j
    from app import llm
    from app.brainjobs import BrainJobs, strip_numbers
    from app.db import DB
    from app.feeds import Feeds
    from app.keys import KeyStore

    assert strip_numbers("Gold rose. It hit 4000 dollars! Fed is calm.") == "Gold rose. Fed is calm."
    answer = {"mood": "Fed sakitdir. Qızıl 4000-ə çatdı.",
              "items": [{"title": "Fed hints at cut", "url": "https://x.com/a/1", "source": "@fed", "metals": ["XAU", "ZZZ"],
                         "direction": "up", "strength": 5, "why": "Faiz enə bilər."}]}

    class R:
        status_code = 200
        def json(self):
            return {"output": [{"type": "x_search_call"}, {"type": "web_search_call"},
                               {"type": "message", "content": [{"type": "output_text", "text": "Here:\n" + _j.dumps(answer)}]}],
                    "usage": {"input_tokens": 100, "output_tokens": 50}}

    class C:
        def __init__(self, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, headers=None, json=None):
            assert url.endswith("/v1/responses") and json["tools"] == [{"type": "x_search"}]
            return R()

    monkeypatch.setattr(llm.httpx, "AsyncClient", C)
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    ks.set("xai", {"key": "xai-test-123456"})
    jobs = BrainJobs(db, ks, Feeds(db, ks))
    assert asyncio.run(jobs.scout(1_800_000_000)) == 1
    last = jobs.last_scout()
    it = last["items"][0]
    assert it["metals"] == ["XAU"] and it["strength"] == 3 and last["mood"] == "Fed sakitdir."
    assert db.execute("SELECT COUNT(*) FROM news WHERE source LIKE 'Grok%'").fetchone()[0] == 1
    spent = db.execute("SELECT usd FROM brain_calls").fetchone()[0]
    assert spent > 2 * llm.SEARCH_CALL_USD - 1e-9
