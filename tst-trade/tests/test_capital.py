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
