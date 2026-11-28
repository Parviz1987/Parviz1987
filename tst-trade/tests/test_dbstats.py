"""CME open interest and volume through Databento (owner 28.11): first only the free price question."""
import asyncio

import httpx

from app import dbstats
from app.db import DB
from app.keys import KeyStore

REAL = httpx.AsyncClient


def test_the_price_is_asked_for_every_futures_contract_of_the_four_metals(monkeypatch):
    asked = []

    def handler(req):
        asked.append(dict(req.url.params))
        return httpx.Response(200, json=0.42)
    monkeypatch.setattr(dbstats.httpx, "AsyncClient", lambda **kw: REAL(transport=httpx.MockTransport(handler)))
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    ks.set("databento", {"key": "db-test-key-12345"})
    out = asyncio.run(dbstats.quote(db, ks, now=1795844400))
    assert out["ok"] and set(out["cost_usd"]) == {"1 gün", "1 il", "5 il"}
    assert all(a["schema"] == "statistics" and a["stype_in"] == "parent" and "GC.FUT" in a["symbols"] for a in asked)
    assert {a["start"] for a in asked} == {"2026-11-25", "2025-11-26", "2021-11-26"}


HEAD = "ts_recv,ts_event,rtype,publisher_id,instrument_id,ts_ref,price,quantity,sequence,ts_in_delta,stat_type,channel_id,update_action,stat_flags"


def _ns(day):
    from datetime import datetime, timezone
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1e9)


def test_open_interest_is_summed_over_contracts_per_day():
    rows = [HEAD,
            f"0,{_ns('2026-11-25') + 9},24,1,101,{_ns('2026-11-24')},,300000,1,0,9,0,1,0",
            f"0,{_ns('2026-11-25') + 9},24,1,102,{_ns('2026-11-24')},,50000,1,0,9,0,1,0",
            f"0,{_ns('2026-11-25') + 9},24,1,101,{_ns('2026-11-24')},,310000,2,0,9,0,1,0",      # a correction: last counts
            f"0,{_ns('2026-11-25') + 9},24,1,103,{_ns('2026-11-24')},4000.5,7,3,0,3,0,1,0",     # a settlement: ignored
            f"0,{_ns('2026-11-26') + 9},24,1,101,18446744073709551615,,320000,4,0,9,0,1,0"]     # no reference: event day
    out = dbstats.parse_oi(rows)
    assert out == {"2026-11-24": (360000, 2), "2026-11-26": (320000, 1)}


def test_a_metal_already_stored_is_never_bought_again(monkeypatch):
    db = DB(":memory:")
    paid = []
    monkeypatch.setattr(dbstats, "_cost", lambda key, sym, a, b: paid.append((sym, a)) or (0.3 if a < "2026" else 0.001))
    monkeypatch.setattr(dbstats, "_download", lambda key, sym, a, b: {"2026-11-20": (100, 3), "2026-11-26": (110, 3)})
    out = dbstats.load(db, "k", now=1795844400)
    assert all(a < "2022" for _, a in paid) and len(paid) == 4                     # five years, each metal once
    paid.clear()
    dbstats.load(db, "k", now=1795844400 + 86400)
    assert {a for _, a in paid} == {"2026-11-26"}                                  # only the days since the last one
    assert float(db.get(dbstats.SPENT)) > 1.2


def test_the_rule_waits_a_day_for_the_published_open_interest():
    db = DB(":memory:")
    db.script(dbstats.SCHEMA)
    from datetime import datetime, timezone
    px = [100, 101, 102, 103, 104, 105, 106]                    # gold rises every day
    for k, p in enumerate(px):
        t = int(datetime(2026, 11, 2 + k, tzinfo=timezone.utc).timestamp())
        db.execute("INSERT INTO candles(symbol, tf, t, o, h, l, c) VALUES('XAU','1d',?,?,?,?,?)", (t, p, p, p, p))
        db.execute("INSERT INTO cme_oi VALUES('XAU', ?, ?, 5)", (f"2026-11-{2 + k:02d}", 1000 + k * 10))   # OI rises
    out = dbstats.evaluate(db)
    assert out["n"] == 4 and out["hit_rate"] == 1.0 and out["status"] == "az"      # continuation, long, all right
    assert out["first"] == "2026-11-03"
