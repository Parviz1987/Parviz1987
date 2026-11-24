import json

from app import candles
from app.db import DB
from app.engine import Engine
from app.keys import KeyStore
from app.providers.base import Quote
from app.providers.capital import quote_of


def test_quote_of():
    raw = json.dumps({"destination": "quote", "payload": {"epic": "GOLD", "bid": 3600.1, "ofr": 3600.5,
                                                          "timestamp": 1795400000000}})
    q = quote_of(raw)
    assert q["symbol"] == "XAU" and q["mid"] == 3600.3 and q["ts"] == 1795400000.0
    assert quote_of(json.dumps({"destination": "ping"})) is None
    assert quote_of(json.dumps({"destination": "quote", "payload": {"epic": "OIL", "bid": 1, "ofr": 2}})) is None
    assert quote_of("not json") is None


def test_stream_quote_builds_candle_at_once():
    db = DB(":memory:")
    eng = Engine(db, KeyStore(db, "s" * 64), "goldapi", 15)
    eng.on_quote(Quote(symbol="XAG", price=42.1, source_ts=1795400000.0))
    eng.on_quote(Quote(symbol="XAG", price=42.3, source_ts=1795400001.0))
    c = candles.get(db, "XAG", "1m")[-1]
    assert c["h"] == 42.3 and eng.quotes["XAG"]["price"] == 42.3


def test_capital_slot_needs_three_fields():
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    try:
        ks.set("capital", {"api_key": "k"})
        raise AssertionError("should fail")
    except ValueError:
        pass
    ks.set("capital", {"api_key": "k1234567", "login": "a@b.c", "password": "pw123456"})
    assert set(ks.get("capital")) == {"api_key", "login", "password"}


def test_history_walks_back_page_by_page():
    """The broker gives 1000 candles a request; older ones come by date range until the limit is reached."""
    import asyncio
    from datetime import datetime, timezone
    from app.providers import capital as cap

    def page(t_end, n):
        return {"prices": [{"snapshotTimeUTC": datetime.fromtimestamp(t_end - (n - 1 - i) * 900, timezone.utc)
                            .strftime("%Y-%m-%dT%H:%M:%S"),
                            **{k: {"bid": 100.0, "ask": 100.2} for k in ("openPrice", "highPrice", "lowPrice",
                                                                         "closePrice")}} for i in range(n)]}

    class Resp:
        def __init__(self, data):
            self.status_code, self._d = 200, data

        def json(self):
            return self._d

    calls = []
    t_last = 1_800_000_000 // 900 * 900 + 3 * 86400       # a weekday

    class Client:
        async def get(self, url, params=None, headers=None):
            calls.append(params)
            if "to" not in params:
                return Resp(page(t_last, 1000))
            to = int(datetime.strptime(params["to"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
            return Resp(page(to, 1000))

    h = cap.CapitalHistory({"identifier": "x", "password": "y", "api_key": "z"})
    h.client, h.tokens, h.request_gap = Client(), {"X": "1"}, 0
    h.epics = {"XAU": "GOLD"}
    rows = asyncio.run(h.candles("XAU", "15m", 2500))
    assert len(rows) == 2500 and len(calls) == 3
    ts = [r[0] for r in rows]
    assert ts == sorted(ts) and len(set(ts)) == len(ts)
