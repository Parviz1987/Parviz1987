"""AMFI: India's gold ETF net flow from the official monthly report (one number per month, known by the 15th)."""
import asyncio
from datetime import datetime, timezone

from app import feeds, fundamental
from app.db import DB
from app.keys import KeyStore

ROWS = [["", "Monthly Report for the month of October 2026"],
        ["Sr", "Scheme Name", "No. of Schemes", "Funds Mobilized", "Redemption", "Net Inflow (+ve)/Outflow (-ve)"],
        ["i", "Overnight Fund", 40, 1.0, 2.0, -1.0],
        ["iv", "Gold ETF", 26, 4451.34, 977.32, 3474.03]]


def test_rows_parser():
    assert feeds.amfi_gold_from_rows(ROWS) == 3474.03
    assert feeds.amfi_gold_from_rows(ROWS[:3]) is None


class _R:
    def __init__(self, code):
        self.status_code, self.content = code, b"x"


class _Client:
    def __init__(self):
        self.urls = []

    async def get(self, url, headers=None):
        self.urls.append(url)
        return _R(404 if "nov2026" in url else 200)


def test_job_backfills_gently_and_dates_honestly(monkeypatch):
    db = DB(":memory:")
    f = feeds.Feeds(db, KeyStore(db, "s" * 64))
    monkeypatch.setattr(feeds, "parse_amfi_gold", lambda raw: 100.0)
    now = datetime(2026, 12, 3, tzinfo=timezone.utc).timestamp()
    c = _Client()
    asyncio.run(f.amfi(c, now))
    assert len(c.urls) == 14 and "amnov2026repo" in c.urls[0]           # 2 newest + 12 history
    rows = {r["month"]: r for r in db.execute("SELECT * FROM india_etf").fetchall()}
    assert "2026-11" not in rows                                         # not published yet (404)
    assert rows["2026-10"]["known_ts"] == datetime(2026, 11, 15, tzinfo=timezone.utc).timestamp()
    assert rows["2025-12"]["known_ts"] == datetime(2026, 1, 15, tzinfo=timezone.utc).timestamp()
    d = fundamental.Data(db)
    assert d.ind_etf and d.ind_etf[0][2] == 100.0
