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


def test_xlsx_under_an_xls_name():
    import io
    import zipfile
    ss = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Scheme Name</t></si>'
          '<si><t>Net Inflow (+ve)/Outflow (-ve)</t></si><si><t>Gold ETF</t></si></sst>')
    sh = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
          '<row r="1"><c r="B1" t="s"><v>0</v></c><c r="D1" t="s"><v>1</v></c></row>'
          '<row r="2"><c r="B2" t="s"><v>2</v></c><c r="C2"><v>26</v></c><c r="D2"><v>291.91</v></c></row>'
          '</sheetData></worksheet>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("xl/sharedStrings.xml", ss)
        z.writestr("xl/worksheets/sheet1.xml", sh)
    assert feeds.parse_amfi_gold(b.getvalue()) == 291.91


def test_hunter_stage_counts_official_actuals_too():
    import time
    from app import official, pipeline, surprise
    db = DB(":memory:")
    feeds.Feeds(db, KeyStore(db, "s" * 64))
    surprise.ensure(db)
    now = time.time()
    db.put("hunter:since", str(now - 86400))
    ts = now - 3 * 3600
    db.execute("INSERT INTO events(uid, ts, country, impact, title, forecast) VALUES('x', ?, 'USD', 'High', 'Prelim GDP q/q', '1.5%')", (ts,))
    uid = official.uid_of("Prelim GDP q/q", ts)
    surprise.store(db, [{"uid": uid, "ts": ts, "event": "Prelim GDP q/q", "impact": "High", "estimate": 1.5,
                         "previous": None, "actual": 1.8, "raw_date": "", "known_ts": now}])
    assert official.plan("Prelim GDP Price Index q/q")[1] == "A191RI1Q225SBEA"
    assert pipeline.release_counts(db, now, now - 86400) == (1, 1, 0)       # known from the agency, not missed


def test_geo_place_is_local_and_never_for_private_addresses(tmp_path):
    from app import geo
    assert geo.place("192.168.1.5", tmp_path / "x.sqlite3") is None
    assert geo.place("not-an-ip", tmp_path / "x.sqlite3") is None
    assert geo.place("8.8.8.8", tmp_path / "x.sqlite3") is None            # no file yet: no place, no error
    assert geo.stale(tmp_path / "x.sqlite3")
    assert geo.label({"city": "Baku", "country": "Azerbaijan"}) == "Baku, Azerbaijan" and geo.label(None) == "—"


def test_agent_periods_match_at_the_coarser_precision():
    from app.reporter import _same_period
    assert _same_period("2026-10", "2026-10-31") and _same_period("2026-11-26", "2026-11-26")
    assert not _same_period("2026-10", "2026-11-02") and not _same_period("2026-11-25", "2026-11-26")
