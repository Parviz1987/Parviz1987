"""Owner 28.11: the big players' free data on the Bazar axını page, the Capital.com client sentiment (pre-registered
contrarian test), and Databento's live feed shown as decided off instead of a daily red error."""
import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app import bigplayers, sentiment
from app.db import DB

NY = ZoneInfo("America/New_York")
REAL = httpx.AsyncClient


def test_an_empty_database_gives_an_empty_page_not_an_error():
    out = bigplayers.summary(DB(":memory:"))
    assert out["cot"] == {} and out["gld"] is None and out["central_banks"] == [] and out["sentiment_test"]["status"] == "az"


def test_the_newest_reading_of_each_source():
    db = DB(":memory:")
    db.script("""CREATE TABLE cot (symbol TEXT, d TEXT, oi REAL, mm_long REAL, mm_short REAL, pm_long REAL, pm_short REAL);
                 CREATE TABLE etf_gold (fund TEXT, d TEXT, tonnes REAL);
                 CREATE TABLE cb_gold (country TEXT, period TEXT, oz REAL);""")
    for k in range(30):
        db.execute("INSERT INTO cot VALUES('XAU', ?, 500000, ?, 50000, 0, 0)", (f"2026-{1 + k // 4:02d}-{1 + k % 4 * 7:02d}", 100000 + k * 1000))
        db.execute("INSERT INTO etf_gold VALUES('GLD', ?, ?)", (f"2026-10-{1 + k:02d}", 1000 + k))
    for c in "ABCDEF":
        db.execute("INSERT INTO cb_gold VALUES(?, '2026-09', 1000000)", (c,))
        db.execute("INSERT INTO cb_gold VALUES(?, '2026-10', 1032150.7466)", (c,))
    out = bigplayers.summary(db)
    assert out["cot"]["XAU"]["net"] == 79000 and out["cot"]["XAU"]["change"] == 1000 and out["cot"]["XAU"]["rank_3y"] == 1.0
    assert out["gld"]["tonnes"] == 1029 and out["gld"]["ch_1d"] == 1 and out["gld"]["ch_20d"] == 20
    assert out["central_banks"] == [{"month": "2026-10", "tonnes": 6.0, "banks": 6}]


class _Prov:
    tokens = {"CST": "c", "X-SECURITY-TOKEN": "s"}
    env = "real"


class _Eng:
    provider_name = "capital"
    provider = _Prov()


def test_the_sentiment_uses_the_streams_session_and_is_stored(monkeypatch):
    seen = []

    def handler(req):
        seen.append((req.url.path, dict(req.url.params), req.headers.get("CST")))
        return httpx.Response(200, json={"clientSentiments": [
            {"marketId": "GOLD", "longPositionPercentage": 71.5, "shortPositionPercentage": 28.5},
            {"marketId": "SILVER", "longPositionPercentage": 88.0, "shortPositionPercentage": 12.0}]})
    monkeypatch.setattr(sentiment.httpx, "AsyncClient", lambda **kw: REAL(transport=httpx.MockTransport(handler)))
    db = DB(":memory:")
    assert asyncio.run(sentiment.fetch_once(db, _Eng(), now=1795850000)) == "ok"
    assert seen[0][0].endswith("/clientsentiment") and "GOLD" in seen[0][1]["marketIds"] and seen[0][2] == "c"
    got = sentiment.latest(db)["metals"]
    assert got["XAU"]["long_pct"] == 71.5 and got["XAG"]["long_pct"] == 88.0
    class _NoSession(_Eng):
        provider = type("P", (), {"tokens": None})()
    assert asyncio.run(sentiment.fetch_once(db, _NoSession())) == "no session"        # never logs in on its own


def test_the_contrarian_test_reads_one_noon_reading_a_day_and_needs_60():
    db = DB(":memory:")
    db.script(sentiment.SCHEMA)
    base = datetime(2026, 12, 1, 12, 5, tzinfo=NY).timestamp()       # a Tuesday
    for k in range(70):
        t = int(base + k * 86400)
        db.execute("INSERT INTO sentiment VALUES('XAU', ?, 75)", (t,))           # the crowd long → expect down
        db.execute("INSERT INTO sentiment VALUES('XAU', ?, 20)", (t - 3 * 3600,))  # 09:05: not the noon reading
        h0 = (t // 3600 + 1) * 3600
        for j in range(26):
            p = 4000 - j * 2                                                     # gold falls after each reading
            db.execute("INSERT OR REPLACE INTO candles(symbol, tf, t, o, h, l, c) VALUES('XAU','1h',?,?,?,?,?)",
                       (h0 + j * 3600, p, p, p - 2, p - 2))
    days = sentiment.daily(db)
    assert all(pct == 75 for _, pct in days)
    out = sentiment.evaluate(db, now=base + 120 * 86400)
    assert out["n"] >= 30 and out["hit_rate"] == 1.0
    assert out["status"] == ("sübut" if out["n"] >= 60 else "az")
