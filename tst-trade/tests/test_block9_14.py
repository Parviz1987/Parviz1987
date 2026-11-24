"""Block 9 (official actuals, Fed odds, ETF proxies) and Block 14 (nightly backup)."""
import asyncio
import gzip
import json
import sqlite3
from datetime import datetime, timezone

from app import backup, official, surprise
from app.db import DB
from app.feeds import Feeds
from app.keys import KeyStore


def ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()


def test_official_figures_are_computed_as_forex_factory_states_them():
    bls = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [
        {"seriesID": "CUSR0000SA0", "data": [{"year": "2026", "period": "M10", "value": "330.0", "latest": "true"},
                                             {"year": "2026", "period": "M09", "value": "329.0"},
                                             {"year": "2026", "period": "M13", "value": "1"}]},
        {"seriesID": "CES0000000001", "data": [{"year": "2026", "period": "M10", "value": "160250"},
                                               {"year": "2026", "period": "M09", "value": "160000"}]}]}}
    s = official.parse_bls(bls)
    per, v = official.compute("mm", s["CUSR0000SA0"])
    assert per == "2026-10" and v == 0.3
    assert official.compute("chg", s["CES0000000001"]) == ("2026-10", 250)
    release = ts("2026-11-13 13:30")
    assert official.period_ok("mm", "CUSR0000SA0", "2026-10", release)
    assert not official.period_ok("mm", "CUSR0000SA0", "2026-09", release)     # last month's figure: never taken
    assert official.plan("Core CPI m/m")[1] == "CUSR0000SA0L1E" and official.plan("CPI m/m")[1] == "CUSR0000SA0"
    assert official.plan("Unemployment Claims")[0] == "fred" and official.plan("Retail Sales m/m") is None


def test_official_job_stores_the_actual_with_the_time_it_became_known(monkeypatch):
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    f = Feeds(db, ks)
    surprise.ensure(db)
    now = ts("2026-11-13 13:32")
    db.execute("INSERT INTO events(title, country, ts, impact, forecast, previous, actual) VALUES"
               "('CPI m/m', 'USD', ?, 'High', '0.2%', '0.4%', NULL)", (ts("2026-11-13 13:30"),))

    class Resp:
        def json(self):
            return {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"seriesID": "CUSR0000SA0", "data": [
                {"year": "2026", "period": "M10", "value": "330.99"}, {"year": "2026", "period": "M09", "value": "330.0"}]}]}}

    class Client:
        async def post(self, url, json=None, headers=None):
            return Resp()
    monkeypatch.setattr("time.time", lambda: now)
    asyncio.run(f.official(Client()))
    r = db.execute("SELECT actual, estimate, known_ts FROM releases").fetchone()
    assert r["actual"] == 0.3 and r["estimate"] == 0.2 and r["known_ts"] == now
    assert f.health("official")["ok"] is True


def test_backup_copy_and_signature(tmp_path):
    p = tmp_path / "t.sqlite3"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE x(a)")
    c.execute("INSERT INTO x VALUES (42)")
    c.commit()
    c.close()
    gz = backup.make_copy(str(p), str(tmp_path / "b"))
    raw = gzip.open(gz).read()
    assert raw.startswith(b"SQLite format 3")
    creds = {"account_id": "acc", "access_key_id": "AK", "secret_access_key": "SK", "bucket": "b"}
    now = datetime(2026, 11, 24, 7, 0, tzinfo=timezone.utc)
    url, h = backup._headers(creds, "PUT", "/b/backups/x.gz", "abc", now=now)
    assert url == "https://acc.r2.cloudflarestorage.com/b/backups/x.gz"
    assert h["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AK/20261124/auto/s3/aws4_request")
    assert h["Authorization"] == backup._headers(creds, "PUT", "/b/backups/x.gz", "abc", now=now)[1]["Authorization"]


def test_kalshi_price_in_cents_or_dollars():
    from app.feeds import kalshi_prob
    assert kalshi_prob({"last_price": 45}) == 0.45
    assert kalshi_prob({"last_price_dollars": "0.6200"}) == 0.62
    assert kalshi_prob({"last_price": 0, "yes_bid": 10, "yes_ask": 14}) == 0.12
    assert kalshi_prob({"yes_bid_dollars": "0.30", "yes_ask_dollars": "0.40"}) == 0.35
    assert kalshi_prob({}) is None
