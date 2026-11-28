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


def _feed(study, rows):
    for r in rows:
        study.add(*r)


def test_the_rule_takes_entry_a_minute_after_the_alarm_and_skips_a_contract_roll():
    s = dbhist.Study()
    t = 1_700_000_000 - 1_700_000_000 % 3600
    rows = [(t + i * 0.5, 1, 4000.0, 1, "B") for i in range(1200)]         # 1 200 small trades: the line stays 20
    rows.append((t + 610.2, 1, 4000.0, 60, "B"))                          # an alarm: 60 lots >= 2 x 20, buyer
    rows += [(t + 620 + i * 10, 1, 4000.0 + (2.0 if i > 4 else 0), 1, "A") for i in range(400)]   # rises after entry
    _feed(s, rows)
    s.finish()
    a = s.done[0]
    assert a["side"] == 1 and a["m0"] == t + 660 and a["entry"] == 4000.0 and a["exit15"] == 4002.0
    # the same alarm when the exit falls in the next contract: not counted
    s2 = dbhist.Study()
    _feed(s2, rows[:1201] + [(x[0], 2 if x[0] > t + 900 else 1, *x[2:]) for x in rows[1201:]])
    s2.finish()
    assert all(a.get("exit15") is None for a in s2.done)


def test_the_verdict_needs_enough_alarms_both_halves_and_the_cost():
    def al(k, up):
        return {"ts": k, "side": 1, "entry": 100.0, "exit15": 100.0 * (1.002 if up else 0.999), "exit60": 100.1}
    few = dbhist.verdict([al(k, True) for k in range(50)])
    assert few["status"] == "az"
    good = dbhist.verdict([al(k, k % 10 < 7) for k in range(200)])
    assert good["status"] == "sübut" and good["m15"]["n"] == 200
    late = dbhist.verdict([al(k, k >= 100 and k % 10 < 9) for k in range(200)])   # only the second half works
    assert late["status"] == "yox"


def test_the_download_stops_at_the_owners_ceiling(monkeypatch):
    db = DB(":memory:")
    monkeypatch.setattr(dbhist, "_cost", lambda key, a, b: 4.0)            # 12 x 4 = 48 > 35
    streamed = []
    monkeypatch.setattr(dbhist, "_stream_month", lambda *a, **k: streamed.append(a[1]) or 10)
    out = dbhist.download_and_measure(db, "db-key")
    assert not out["done"] and "tavan" in out["stopped"] and len(streamed) == 8      # 8 x 4 = 32; the 9th would pass 35
    out2 = dbhist.download_and_measure(db, "db-key")                       # the paid months are not paid again
    assert len(streamed) == 8 and "tavan" in out2["stopped"]
