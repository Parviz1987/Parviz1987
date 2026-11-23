import asyncio

from app.db import DB
from app.engine import Engine
from app.keys import KeyStore
from app.providers.base import HistoryProvider

SECRET = "s" * 64


class Fake(HistoryProvider):
    name = "capital"

    def __init__(self):
        self.calls = 0

    async def candles(self, symbol, tf, limit):
        self.calls += 1
        return [(1_700_000_000 // 60 * 60, 1.0, 1.0, 1.0, 1.0)]


def test_new_source_loads_at_once_and_old_state_waits():
    db = DB(":memory:")
    eng = Engine(db, KeyStore(db, SECRET), "goldapi", 15)
    fake = Fake()
    eng._history_names = lambda: ["capital"]
    eng._history_sources = lambda: [(fake, True)]
    eng.history_state = {"ts": 0, "source": "twelvedata"}       # old state from another source, long ago
    asyncio.run(eng.backfill())
    assert fake.calls > 0 and eng.history_state["source"] == "capital"
    n = fake.calls
    asyncio.run(eng.backfill())                                  # same source, just loaded: nothing to do
    assert fake.calls == n
