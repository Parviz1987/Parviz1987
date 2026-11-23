import json
import math
import random

from app import candles, forecast, markets
from app.db import DB
from app.engine import Engine
from app.keys import KeyStore


def test_impulse_sees_a_move_the_metal_has_not_followed():
    rng = random.Random(2)
    x, g = [100.0], [100.0]
    for _ in range(120):                       # gold moves with the dollar proxy in the same candle (beta 1)
        r = rng.gauss(0, 0.001)
        x.append(x[-1] * math.exp(r))
        g.append(g[-1] * math.exp(r + rng.gauss(0, 0.0003)))
    x.append(x[-1] * math.exp(0.004))          # the proxy jumps, gold stays flat
    g.append(g[-1])
    p, basis = markets.impulse_view(g, x, "EUR/USD")
    assert p > 0.55 and "yetişməsi" in basis
    p2, _ = markets.impulse_view(g[:-1] + [g[-2] * math.exp(0.004)], x, "EUR/USD")   # gold followed: no view
    assert p2 == 0.5
    noise = [100 * math.exp(rng.gauss(0, 0.001)) for _ in range(122)]
    assert markets.impulse_view(noise, x, "EUR/USD")[0] == 0.5                       # no link: no view


def test_related_closes_align_and_feed_the_methods():
    db = DB(":memory:")
    eng = Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    db.put("related:epics", json.dumps({"ts": 1, "epics": {"EURUSD": "EURUSD"}}))
    t0 = 1_700_000_000 // 900 * 900
    for i in range(130):
        candles.store_history(db, "XAU", "15m", [(t0 + i * 900, 100, 100, 100, 100 + i * 0.01)])
        candles.store_history(db, "EURUSD", "15m", [(t0 + i * 900, 1, 1, 1, 1 + i * 0.0001)])
    now = t0 + 130 * 900 + 5
    past = candles.closed(db, "XAU", "15m", now, limit=200)
    rel = eng.related_closes(past, "15m", now)
    assert "dollar" in rel and "oil" not in rel and len(rel["dollar"][0]) == len(rel["dollar"][1]) == 101
    m = forecast.build(past, "15m", related=rel)["methods"]
    assert "dollar" in m and m["oil"]["p_up"] == 0.5
    assert "dollar" not in forecast.build(past, "1w")["methods"]


def test_dollar_falls_back_to_eurusd_when_the_index_is_quiet():
    db = DB(":memory:")
    eng = Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    db.put("related:epics", json.dumps({"ts": 1, "epics": {"DXY": "DXY", "EURUSD": "EURUSD"}}))
    t0 = 1_700_000_000 // 900 * 900
    for i in range(130):
        candles.store_history(db, "XAU", "15m", [(t0 + i * 900, 100, 100, 100, 100 + i * 0.01)])
        candles.store_history(db, "EURUSD", "15m", [(t0 + i * 900, 1, 1, 1, 1 + i * 0.0001)])
        if i < 120:                                   # the index stopped quoting 10 candles ago
            candles.store_history(db, "DXY", "15m", [(t0 + i * 900, 99, 99, 99, 99 - i * 0.01)])
    now = t0 + 130 * 900 + 5
    rel = eng.related_closes(candles.closed(db, "XAU", "15m", now, limit=200), "15m", now)
    assert rel["dollar"][2] == "EUR/USD"


def test_dollar_takes_the_market_most_linked_to_the_metal():
    rng = random.Random(4)
    db = DB(":memory:")
    eng = Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    db.put("related:epics", json.dumps({"ts": 1, "epics": {"DXY": "DXY", "EURUSD": "EURUSD"}}))
    t0 = 1_700_000_000 // 900 * 900
    g = e = d = 100.0
    for i in range(130):
        r = rng.gauss(0, 0.001)
        g *= math.exp(r)
        e *= math.exp(r + rng.gauss(0, 0.0002))           # EUR/USD moves with gold
        d *= math.exp(rng.gauss(0, 0.001))                # the index wanders on its own
        for sym, px in (("XAU", g), ("EURUSD", e), ("DXY", d)):
            candles.store_history(db, sym, "15m", [(t0 + i * 900, px, px, px, px)])
    now = t0 + 130 * 900 + 5
    rel = eng.related_closes(candles.closed(db, "XAU", "15m", now, limit=200), "15m", now)
    assert rel["dollar"][2] == "EUR/USD"
