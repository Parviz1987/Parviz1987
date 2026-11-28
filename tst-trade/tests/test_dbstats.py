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
