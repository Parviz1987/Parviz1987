"""Plan 27.11 step 9: at a scheduled US release the agency's own figure is fetched every few seconds and raises its
alarm at once; every headline records when it arrived, so each source's real delay is measured."""
import asyncio
import json
import time

from app import pipeline, signals
from app.brainjobs import BrainJobs
from app.db import DB
from app.engine import Engine
from app.feeds import Feeds
from app.keys import KeyStore


def _setup():
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    feeds = Feeds(db, ks)
    return db, ks, feeds


def test_next_target_is_a_bls_release_or_a_fed_decision():
    db, ks, f = _setup()
    now = time.time()
    db.execute("INSERT INTO events(uid, title, country, ts, impact, forecast) VALUES('a', 'CPI m/m', 'USD', ?, 'High', '0.3%')",
               (now + 600,))
    assert f.next_target(now) == (now + 600, "bls")
    db.execute("DELETE FROM events")
    db.execute("INSERT INTO events(uid, title, country, ts, impact, forecast) VALUES('b', 'Federal Funds Rate', 'USD', ?, "
               "'High', '3.75%')", (now + 60,))
    assert f.next_target(now)[1] == "fed"


def test_the_release_minute_fetch_stores_the_figure_and_raises_the_alarm_at_once():
    db, ks, f = _setup()
    now = time.time()
    ts = now - 5                                            # the release was 5 seconds ago: the normal round waits 30 s
    db.execute("INSERT INTO events(uid, title, country, ts, impact, forecast) VALUES('a', 'CPI m/m', 'USD', ?, 'High', '0.3%')",
               (ts,))
    from app import official as off
    per = off.expected_period("mm", "CUSR0000SA0", ts)
    y, m = int(per[:4]), int(per[5:])
    prev = f"{y if m > 1 else y - 1}-{(m - 1) or 12:02d}"
    body = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"seriesID": "CUSR0000SA0", "data": [
        {"year": per[:4], "period": "M" + per[5:], "value": "100.5"},
        {"year": prev[:4], "period": "M" + prev[5:], "value": "100.0"}]}]}}

    class R:
        def json(self):
            return body

    class C:
        async def post(self, url, json=None, headers=None):
            return R()
    assert asyncio.run(f.official(C(), sniping=True)) == 1
    alarm = [s for s in signals.recent(db) if s["kind"] == "release"]
    assert alarm and "rəsmi mənbədən" in alarm[0]["text"] and alarm[0]["strength"] == 3
    assert json.loads(db.get("official:last_delay"))["seconds"] < 60


def test_each_headline_records_its_arrival_and_the_link_map_shows_the_delay():
    db, ks, f = _setup()
    now = time.time()

    async def fake_get(client, url, headers=None, **kw):
        t = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(now - 600))
        return (f"<rss><channel><item><title>Gold rises</title><link>https://x/1</link><pubDate>{t}</pubDate></item>"
                "</channel></rss>").encode()
    f._get = fake_get
    asyncio.run(f.news(None))
    r = db.execute("SELECT ts, received_ts FROM news LIMIT 1").fetchone()
    assert r["received_ts"] is not None and 550 < r["received_ts"] - r["ts"] < 700
    jobs = BrainJobs(db, ks, f)
    rows = {x["stage"]: x for x in pipeline.check(db, ks, Engine(db, ks, "demo", 15, f, jobs), f, jobs, now)}
    assert "Google News: 10 dəq" in rows["Xəbər gecikməsi (mənbə-mənbə)"]["msg"]       # one path, not per publisher


def test_a_total_news_outage_is_seen_although_google_is_asked_every_10_minutes():
    # 27.11 review: with Google News every 10 minutes, «errors < all feeds» stayed true in most rounds
    db, ks, f = _setup()

    async def down(client, url, headers=None, **kw):
        raise ValueError("HTTP 503")
    f._get = down
    asyncio.run(f.news(None))          # first round: every feed asked, all fail
    asyncio.run(f.news(None))          # next round: only the Fed feed asked (fails); Google's last result still failed
    assert f.health("rss")["ok"] is False
    assert int(db.get("hc:news_bad")) == 2


def test_a_fed_statement_raised_by_the_sniper_is_not_alarmed_twice():
    db, ks, f = _setup()
    signals.ensure(db)
    now = time.time()
    db.execute("INSERT INTO news(uid, source, url, title, ts, metals) VALUES('u1', 'Federal Reserve', '', 'FOMC statement', ?, '')",
               (now - 60,))
    signals.emit(db, "fed:u1", "news", "Fed: FOMC statement (rəsmi lentdən)", 3, None, now)
    db.script("CREATE TABLE IF NOT EXISTS news_ai (uid TEXT PRIMARY KEY, ts REAL, event TEXT, metals TEXT, "
              "direction TEXT, strength INTEGER, brain TEXT)")          # the layout of app/brainjobs.py
    db.execute("INSERT INTO news_ai(uid, ts, metals, direction, strength) VALUES('u1', ?, 'XAU', 'up', 3)", (now - 30,))
    signals.from_news(db, now)
    assert [s["kind"] for s in signals.recent(db)].count("news") == 1


def test_spikes_need_ten_unbroken_minutes_before_them():
    db = DB(":memory:")
    signals.ensure(db)
    t0 = int(time.time() // 60) * 60 - 300 * 60
    c, rows = 4000.0, []
    import random
    random.seed(2)
    for i in range(300):
        if 290 <= i < 295:
            continue                    # a 5-minute break right before the last minutes (a reopen)
        c *= 1 + random.gauss(0, 0.0002) + (0.004 if i == 299 else 0)
        rows.append(("XAU", "1m", t0 + i * 60, c, c, c, c))
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'live')", rows)
    assert signals.from_spikes(db, t0 + 300 * 60 + 30, ["XAU"]) == 0
