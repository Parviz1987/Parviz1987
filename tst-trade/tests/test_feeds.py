import time

from app import feeds
from app.db import DB
from app.keys import KeyStore

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Gold slides as dollar firms - Reuters</title><source url="x">Reuters</source>
<link>https://news.example/a</link><pubDate>Mon, 23 Nov 2026 04:00:00 GMT</pubDate></item>
<item><title>Silver and platinum steady</title><link>https://news.example/b</link>
<pubDate>Mon, 23 Nov 2026 03:00:00 GMT</pubDate></item>
<item><title></title><pubDate>Mon, 23 Nov 2026 03:00:00 GMT</pubDate></item>
<item><title>No date here</title></item>
</channel></rss>"""

FF = b"""[{"title":"CPI m/m","country":"USD","date":"2026-11-24T08:30:00-05:00","impact":"High","forecast":"0.3%",
"previous":"0.2%"},{"title":"Bank Holiday","country":"JPY","date":"2026-11-24","impact":"Holiday"},
{"title":"","country":"USD","date":"2026-11-24T08:30:00-05:00"}]"""

FRED = b'{"observations":[{"date":"2026-11-20","value":"1.95"},{"date":"2026-11-19","value":"."}]}'


def test_parse_feed():
    items = feeds.parse_feed(RSS, "test")
    assert [i["title"] for i in items] == ["Gold slides as dollar firms", "Silver and platinum steady"]
    assert items[0]["source"] == "Reuters" and items[0]["metals"] == "XAU"
    assert items[1]["metals"] == "XAG,XPT"


def test_parse_ff_and_event_mode():
    rows = feeds.parse_ff(FF)
    assert len(rows) == 2
    cpi = rows[0]
    assert cpi["impact"] == "High" and cpi["forecast"] == "0.3%"
    from datetime import datetime, timezone
    assert cpi["ts"] == datetime(2026, 11, 24, 13, 30, tzinfo=timezone.utc).timestamp()
    hol = rows[1]
    assert hol["impact"] == "Holiday"          # bare date read as New York local midnight
    db = DB(":memory:")
    f = feeds.Feeds(db, KeyStore(db, "s" * 64))
    db.executemany("INSERT INTO events(uid, title, country, ts, impact, forecast, previous, actual) "
                   "VALUES(:uid, :title, :country, :ts, :impact, :forecast, :previous, :actual)", rows)
    assert f.event_mode(cpi["ts"] - 600)["title"] == "CPI m/m"
    assert f.event_mode(cpi["ts"] - 3600) is None
    assert f.event_mode(cpi["ts"] + 1700) is not None
    assert [e["title"] for e in f.upcoming(cpi["ts"] - 86400)] == ["CPI m/m"]


def test_parse_fred_skips_missing():
    assert feeds.parse_fred(FRED) == [("2026-11-20", 1.95)]


def test_macro_without_key_reports_it():
    import asyncio
    db = DB(":memory:")
    f = feeds.Feeds(db, KeyStore(db, "s" * 64))

    async def run():
        await f.macro(None)
    asyncio.run(run())
    assert f.health("fred")["ok"] is False and "açar" in f.health("fred")["message"]
    assert f.macro_view()[0]["value"] is None
    assert time.time() - f.health("fred")["checked"] < 5


def test_parse_cot_rows_and_field_change():
    from app.feeds import parse_cot
    rows = [{"cftc_contract_market_code": "088691", "report_date_as_yyyy_mm_dd": "2026-11-17T00:00:00.000",
             "open_interest_all": "500000", "m_money_positions_long_all": "200000",
             "m_money_positions_short_all": "50000", "prod_merc_positions_long": "10",
             "prod_merc_positions_short": "20"},
            {"cftc_contract_market_code": "999999", "report_date_as_yyyy_mm_dd": "2026-11-17"}]
    out = parse_cot(rows)
    assert out == [("XAU", "2026-11-17", 500000.0, 200000.0, 50000.0, 10.0, 20.0)]
    try:
        parse_cot([{"cftc_contract_market_code": "088691", "other": 1}])
        raise AssertionError("must fail loudly")
    except ValueError as e:
        assert "sahə" in str(e)
