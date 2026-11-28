"""FinancialJuice headlines (plan 27.11 step 11.1): the provider's message goes into the news table with its arrival
time; a breaking level-3 headline that touches gold / the dollar / the Fed raises one alarm."""
from app import fjnews, signals
from app.db import DB
from app.feeds import Feeds
from app.keys import KeyStore


def _db():
    db = DB(":memory:")
    Feeds(db, KeyStore(db, "s" * 64))           # creates the news table (with received_ts)
    signals.ensure(db)
    return db


def test_a_headline_is_stored_once_with_its_arrival_time():
    db = _db()
    msg = {"seq": 1203, "type": "news", "event": "created", "sent": "2026-10-28T13:45:00Z",
           "data": {"id": 4812, "datePublished": "2026-10-28T13:45:00Z",
                    "title": "Bank of Canada raises overnight interest rate to 2.50%",
                    "labels": ["Canada", "CAD", "Central Banks"], "breaking": True, "level": 3,
                    "link": "https://www.financialjuice.com/news/4812/x"}}
    assert fjnews.handle(db, msg) == 1 and fjnews.handle(db, msg) == 0
    r = db.execute("SELECT source, title, received_ts FROM news WHERE uid='fj:4812'").fetchone()
    assert r["source"] == "FinancialJuice" and r["received_ts"] is not None
    assert not [s for s in signals.recent(db) if s["kind"] == "news"]        # Canada: not gold / dollar / Fed


def test_a_breaking_gold_or_fed_headline_alarms_and_calendar_messages_are_ignored():
    db = _db()
    fjnews.handle(db, {"type": "news", "event": "created", "data": {"id": 1, "title": "Fed's Powell: rate cut possible",
                                                                    "labels": ["USD", "Fed"], "breaking": True,
                                                                    "level": 3, "datePublished": "2026-11-27T19:00:00Z"}})
    fjnews.handle(db, {"type": "calendar", "event": "created", "data": {"id": 2, "title": "US CPI"}})
    s = [x for x in signals.recent(db) if x["kind"] == "news"]
    assert len(s) == 1 and "Powell" in s[0]["text"] and s[0]["strength"] == 3
    assert db.execute("SELECT COUNT(*) FROM news").fetchone()[0] == 1


def test_the_stream_uses_the_key_header_and_reconnects_when_a_new_key_is_saved(monkeypatch):
    """The live loop opens one connection with X-API-Key; a key saved anew in Admin is used on the next connection;
    a bad key (4001) is not hammered; «Yoxla» answers from the open connection instead of opening a second one."""
    import asyncio
    db = _db()
    ks = KeyStore(db, "s" * 64)
    ks.set("financialjuice", {"key": "old"})
    seen = []

    class Closed(Exception):
        def __init__(self, code):
            self.code = code

    class WS:
        def __init__(self, key):
            self.key, self.n = key, 0

        async def __aenter__(self):
            if self.key == "bad":
                raise Closed(4001)
            return self

        async def __aexit__(self, *a):
            return False

        async def recv(self):
            self.n += 1
            if self.n == 1:
                return '{"type":"news","event":"created","data":{"id":%d,"title":"Gold jumps","labels":[]}}' % len(seen)
            await asyncio.sleep(3600)

    def fake(key, **kw):
        seen.append(key)
        return WS(key)

    monkeypatch.setattr(fjnews, "_connect", fake)
    clock = [1000.0]
    monkeypatch.setattr(fjnews.time, "time", lambda: clock[0])
    real_wait = asyncio.wait_for

    async def fast_wait(aw, timeout):
        clock[0] += 61
        try:
            return await real_wait(aw, 0.01)
        except asyncio.TimeoutError:
            raise

    monkeypatch.setattr(fjnews.asyncio, "wait_for", fast_wait)

    async def body():
        task = asyncio.ensure_future(fjnews.run(db, ks))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if fjnews._live.get("got"):
                break
        assert seen == ["old"] and fjnews._live.get("key") == "old"
        ok, msg = await fjnews.check({"key": "old"})
        assert ok and "açıqdır" in msg and seen == ["old"]          # no second connection
        ks.set("financialjuice", {"key": "new"})
        for _ in range(100):
            await asyncio.sleep(0.02)
            if "new" in seen:
                break
        assert seen[-1] == "new"
        task.cancel()

    asyncio.run(body())
    assert db.execute("SELECT COUNT(*) FROM news WHERE source='FinancialJuice'").fetchone()[0] >= 2
