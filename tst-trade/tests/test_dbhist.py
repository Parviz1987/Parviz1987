"""Databento history price list (owner 27.11 23:10: «əvvəl sübut olsun»): a free question, nothing downloaded."""
import asyncio
import json

import httpx

from app import dbhist
from app.db import DB
from app.keys import KeyStore

REAL = httpx.AsyncClient


def test_the_price_list_is_asked_per_window_and_kept(monkeypatch):
    asked = []

    def handler(req):
        asked.append(dict(req.url.params))
        return httpx.Response(200, json=12.5)
    monkeypatch.setattr(dbhist.httpx, "AsyncClient", lambda **kw: REAL(transport=httpx.MockTransport(handler)))
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    ks.set("databento", {"key": "db-test-key-12345"})
    out = asyncio.run(dbhist.quote(db, ks, now=1795831200))
    assert out["ok"] and out["cost_usd"] == {"1 ay": 12.5, "3 ay": 12.5, "6 ay": 12.5, "12 ay": 12.5}
    assert {a["symbols"] for a in asked} == {"GC.v.0"} and all(a["schema"] == "trades" for a in asked)
    assert json.loads(db.get(dbhist.QUOTE))["end"] == "2026-11-26"


def test_no_key_is_said_plainly():
    db = DB(":memory:")
    out = asyncio.run(dbhist.quote(db, KeyStore(db, "s" * 64)))
    assert not out["ok"] and "açarı yoxdur" in out["msg"]
