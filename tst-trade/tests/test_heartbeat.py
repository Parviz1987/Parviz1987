"""Kənar nəzarətçi: with the one key the checks are created on the account (urgent ones on Telegram + e-mail, the rest
on e-mail only), signals are queued and sent without blocking, a closed market sends «atlandı», a stale price in open
hours sends «fail», a rolled-back deploy is reported once, and the diagnostics never show a ping address."""
import asyncio
import json

import httpx

from app import heartbeat
from app.db import DB


class Keys:
    def __init__(self, k):
        self.k = k

    def first(self, slot):
        return self.k if slot == "healthchecks" else None


def _client(log):
    def handler(req: httpx.Request):
        log.append((req.method, str(req.url), req.content.decode() if req.content else ""))
        if req.url.path == "/api/v3/channels/":
            return httpx.Response(200, json={"channels": [{"id": "tg1", "kind": "telegram"},
                                                          {"id": "em1", "kind": "email"}]})
        if req.url.path == "/api/v3/checks/":
            name = json.loads(req.content)["slug"]
            return httpx.Response(201, json={"ping_url": f"https://hc-ping.com/uuid-{name}"})
        return httpx.Response(200, text="OK")
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_setup_creates_checks_with_the_owners_channels():
    db, log = DB(":memory:"), []
    h = heartbeat.Heart(db, Keys("secret-key-123456"))

    async def go():
        async with _client(log) as c:
            r1 = await h.setup(c)
            r2 = await h.setup(c)                  # nothing changed: no second round of calls
            return r1, r2
    r1, r2 = asyncio.run(go())
    assert r1["ok"] and "Telegram kanalı: var" in r1["note"] and r2["note"] == "hazırdır"
    posts = [json.loads(b) for m, u, b in log if m == "POST" and u.endswith("/checks/")]
    assert len(posts) == len(heartbeat.CHECKS)
    by = {p["slug"]: p for p in posts}
    assert by["tst-app-alive"]["channels"] == "tg1,em1" and by["tst-rule-blocks"]["channels"] == "em1"
    assert all(p["unique"] == ["name"] for p in posts)
    assert sum(1 for c in heartbeat.CHECKS if c["urgent"]) == 4


def test_no_key_means_no_calls():
    db, log = DB(":memory:"), []
    h = heartbeat.Heart(db, Keys(None))

    async def go():
        async with _client(log) as c:
            return await h.setup(c)
    assert not asyncio.run(go())["ok"] and log == []


def test_signals_are_sent_with_their_state_and_never_show_addresses():
    db, log = DB(":memory:"), []
    h = heartbeat.Heart(db, Keys("secret-key-123456"))
    h.beat("judge-scoring", "ok", "5 proqnoz")
    h.beat("judge-scoring", "ok", "6 proqnoz")             # the newer one replaces the older in the queue
    h.beat("backup-nightly", "fail", "R2: timeout")
    h.beat("not-a-check", "ok")                            # unknown: ignored

    async def go():
        async with _client(log) as c:
            await h.setup(c)
            return await h.flush(c)
    assert asyncio.run(go()) == 2
    pings = [(u, b) for m, u, b in log if "hc-ping.com" in u]
    assert ("https://hc-ping.com/uuid-tst-judge-scoring", "6 proqnoz") in pings
    assert ("https://hc-ping.com/uuid-tst-backup-nightly/fail", "R2: timeout") in pings
    v = json.dumps(h.view())
    assert "hc-ping.com" not in v and "secret-key" not in v and '"delivered": true' in v


class Eng:
    def __init__(self, last_ok, st="LIVE"):
        self.last_ok, self.st = last_ok, st

    def status(self, s, now):
        return self.st


def test_alive_signals_follow_market_hours():
    import datetime as dt
    db = DB(":memory:")
    h = heartbeat.Heart(db, Keys(None))
    sat = dt.datetime(2026, 11, 28, 12, tzinfo=dt.timezone.utc).timestamp()
    heartbeat.alive_signals(h, Eng(0), sat)
    assert ("app-alive", "ok", "atlandı: bazar bağlıdır") in h.queue
    h.queue.clear()
    tue = dt.datetime(2026, 11, 24, 15, tzinfo=dt.timezone.utc).timestamp()
    heartbeat.alive_signals(h, Eng(tue - 1200), tue)
    assert any(q[0] == "app-alive" and q[1] == "fail" for q in h.queue)
    h.queue.clear()
    heartbeat.alive_signals(h, Eng(tue - 30, "OFFLINE"), tue)
    assert any(q[0] == "price-feed" and q[1] == "fail" for q in h.queue)
    assert any(q[0] == "app-alive" and q[1] == "ok" for q in h.queue)


def test_rolled_back_deploy_is_reported_once(tmp_path):
    db = DB(":memory:")
    h = heartbeat.Heart(db, Keys(None))
    p = tmp_path / "update.log"
    p.write_text("2026-11-26T04:16:48Z updated a -> b, answered after 35 s\n2026-11-27T01:00:00Z c did not answer in "
                 "120 s: rolled back to b\n")
    heartbeat.deploy_signal(h, str(p))
    heartbeat.deploy_signal(h, str(p))                     # a plain restart: not again
    assert [q[1] for q in h.queue if q[0] == "deploy"] == ["fail"]
    p.write_text(p.read_text() + "2026-11-27T02:00:00Z updated b -> d, answered after 5 s\n")
    heartbeat.deploy_signal(h, str(p))
    assert [q[1] for q in h.queue if q[0] == "deploy"][-1] == "ok"
