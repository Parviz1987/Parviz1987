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
    assert r1["ok"] and "Telegram kanalı: var" in r1["note"] and r2["note"].startswith("hazırdır")
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
    h.beat("judge-scoring", "ok", "6 proqnoz")             # within 5 minutes of the last «ok»: not sent again
    h.beat("backup-nightly", "fail", "R2: timeout")
    h.beat("not-a-check", "ok")                            # unknown: ignored

    async def go():
        async with _client(log) as c:
            await h.setup(c)
            return await h.flush(c)
    assert asyncio.run(go()) == 2
    pings = [(u, b) for m, u, b in log if "hc-ping.com" in u]
    assert ("https://hc-ping.com/uuid-tst-judge-scoring", "5 proqnoz") in pings
    assert ("https://hc-ping.com/uuid-tst-backup-nightly/fail", "R2: timeout") in pings
    v = json.dumps(h.view())
    assert "hc-ping.com" not in v and "secret-key" not in v and '"delivered": true' in v


class Eng:
    def __init__(self, last_ok, st="LIVE"):
        self.last_ok, self.st = last_ok, st

    def status(self, s, now):
        return self.st


def test_alive_signals_follow_market_hours_and_need_three_bad_samples():
    import datetime as dt
    db = DB(":memory:")
    h = heartbeat.Heart(db, Keys(None))
    u = lambda *a: dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp()
    sat = u(2026, 11, 28, 12)
    heartbeat.alive_signals(h, Eng(0), sat)
    assert ("app-alive", "ok", "atlandı: bazar bağlıdır") in h.queue
    tue = u(2026, 11, 24, 15)
    h.started = tue - 30                                   # just restarted: no verdict yet (quotes still arriving)
    h.queue.clear()
    h._ok_t.clear()
    heartbeat.alive_signals(h, Eng(None), tue)
    assert h.queue and all(q[2].startswith("atlandı") for q in h.queue)
    h.started = tue - 3600
    reopen = u(2026, 11, 24, 23, 5)                       # 18:05 New York, just after the daily break
    h.queue.clear()
    h._ok_t.clear()
    heartbeat.alive_signals(h, Eng(reopen - 3000), reopen)
    assert all(q[2] == "atlandı: bazar təzə açılıb" for q in h.queue)
    h._ok_t.clear()
    h.queue.clear()
    for k in range(3):                                     # stale price: fail only on the third sample in a row
        heartbeat.alive_signals(h, Eng(tue - 1200), tue + k * 300)
        fails = [q for q in h.queue if q[1] == "fail"]
        assert bool(fails) == (k == 2)
    h.queue.clear()
    h._ok_t.clear()
    heartbeat.alive_signals(h, Eng(tue + 990), tue + 1000)  # one good sample resets the count
    assert h.bad["app-alive"] == 0
    assert any(q[0] == "app-alive" and q[1] == "ok" for q in h.queue)


def test_full_exchange_holidays_are_quiet():
    import datetime as dt
    assert heartbeat.holiday(dt.datetime(2026, 12, 25, 15, tzinfo=dt.timezone.utc).timestamp())
    assert heartbeat.holiday(dt.datetime(2027, 1, 1, 15, tzinfo=dt.timezone.utc).timestamp())
    assert heartbeat.holiday(dt.datetime(2027, 3, 26, 15, tzinfo=dt.timezone.utc).timestamp())   # Good Friday 2027
    assert not heartbeat.holiday(dt.datetime(2026, 11, 26, 15, tzinfo=dt.timezone.utc).timestamp())  # Thanksgiving
    # Christmas Eve: the afternoon and the evening session after the break are quiet too
    db = DB(":memory:")
    h = heartbeat.Heart(db, Keys(None))
    h.started = 0
    for t in (dt.datetime(2026, 12, 24, 19, tzinfo=dt.timezone.utc), dt.datetime(2026, 12, 24, 23, 30, tzinfo=dt.timezone.utc)):
        h.queue.clear(); h._ok_t.clear()
        heartbeat.alive_signals(h, Eng(0), t.timestamp())
        assert h.queue and all(q[2] == "atlandı: birja bayramı" for q in h.queue)


def test_a_feed_that_never_starts_is_reported_after_the_warmup():
    import datetime as dt
    db = DB(":memory:")
    h = heartbeat.Heart(db, Keys(None))
    tue = dt.datetime(2026, 11, 24, 15, tzinfo=dt.timezone.utc).timestamp()
    h.started = tue - 3600
    for k in range(3):
        heartbeat.alive_signals(h, Eng(None, "OFFLINE"), tue + k * 300)
    assert any(q[0] == "app-alive" and q[1] == "fail" for q in h.queue)


def test_new_telegram_channel_sets_up_again_and_failed_signals_are_kept(monkeypatch):
    db, log = DB(":memory:"), []
    h = heartbeat.Heart(db, Keys("secret-key-123456"))
    chans = [{"id": "em1", "kind": "email"}]
    down = {"on": False}

    def handler(req: httpx.Request):
        log.append((req.method, str(req.url)))
        if req.url.path == "/api/v3/channels/":
            return httpx.Response(200, json={"channels": chans})
        if req.url.path == "/api/v3/checks/":
            return httpx.Response(201, json={"ping_url": f"https://hc-ping.com/u-{json.loads(req.content)['slug']}"})
        return httpx.Response(503 if down["on"] else 200, text="x")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            r1 = await h.setup(c)
            chans.append({"id": "tg1", "kind": "telegram"})          # the owner adds Telegram afterwards
            r2 = await h.setup(c)
            down["on"] = True
            h.beat("backup-nightly", "ok", "nüsxə")
            n = await h.flush(c)
            return r1, r2, n

    async def _noop(*_):
        return None
    monkeypatch.setattr(heartbeat.asyncio, "sleep", _noop)
    r1, r2, n = asyncio.run(go())
    assert "YOXDUR" in r1["note"] and "var" in r2["note"] and "quruldu" in r2["note"]
    assert n == 0 and [q[0] for q in h.queue] == ["backup-nightly"]   # not lost: waits for the next round


def test_beats_from_threads_are_safe():
    import threading
    db = DB(":memory:")
    h = heartbeat.Heart(db, Keys(None))
    ts = [threading.Thread(target=lambda c=c: [h.beat(c, "fail", str(i)) for i in range(200)])
          for c in ("backup-nightly", "rule-blocks", "deploy")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(q[0] for q in h.queue) == ["backup-nightly", "deploy", "rule-blocks"]


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


def test_a_held_deploy_is_urgent(tmp_path):
    db = DB(":memory:")
    h = heartbeat.Heart(db, Keys(None))
    p = tmp_path / "update.log"
    p.write_text("2026-11-26T20:49:38Z held 68a8dcb: protected files changed without owner approval: tst-trade/app/judge.py\n")
    heartbeat.deploy_signal(h, str(p))
    assert [q[1] for q in h.queue if q[0] == "deploy"] == ["fail"]
