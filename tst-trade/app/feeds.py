"""Free data collectors: news headlines (RSS, no key), the US economic calendar (Forex Factory export, no key) and
macro series from FRED (free key). Parsers adapted from pj-trade-gold (app/news.py, app/econcal.py).

Each source keeps its health in kv "src:<id>" (last success, last error, rows), so the panel shows what works.
Nothing here is a price: prices come only from the price provider."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import httpx

from . import surprise
from .db import DB
from .keys import KeyStore

log = logging.getLogger("tst.feeds")
NY = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (compatible; tst-trade/1.0)"}
TIMEOUT = 15.0
MAX_BYTES = 2 * 1024 * 1024

NEWS_EVERY, CAL_EVERY, MACRO_EVERY = 120, 3600, 6 * 3600
ALPACA_EVERY = 60
ALPACA_URL = "https://data.alpaca.markets/v1beta1/news"
# Metal funds and miners whose news Benzinga tags: the symbol says which metal the headline is about.
ALPACA_SYMBOLS = {"GLD": "XAU", "IAU": "XAU", "GDX": "XAU", "NEM": "XAU", "SLV": "XAG", "PSLV": "XAG",
                  "PPLT": "XPT", "PALL": "XPD", "SBSW": "XPT"}
NEWS_MAX_AGE = 48 * 3600
NEWS_KEEP = 7 * 86400


def _google_news(q: str) -> str:
    return f"https://news.google.com/rss/search?q={q}+when:1d&hl=en-US&gl=US&ceid=US:en"


NEWS_FEEDS = [
    ("Google News: qızıl", _google_news("gold+price+OR+bullion")),
    ("Google News: gümüş, platin", _google_news("silver+price+OR+platinum+price+OR+palladium+price")),
    ("Google News: Fed və makro",
     _google_news("Federal+Reserve+OR+inflation+OR+%22treasury+yields%22+OR+%22dollar+index%22")),
    ("Google News: geosiyasət", _google_news("gold+sanctions+OR+tariffs+OR+war+OR+geopolitical")),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
]
CAL_URLS = ["https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            "https://nfs.faireconomy.media/ff_calendar_nextweek.json"]
# FRED series: what each means for gold.
MACRO_SERIES = {
    "DFII10": "10 illik real faiz (TIPS), %",
    "DGS10": "10 illik nominal faiz, %",
    "DGS2": "2 illik faiz (Fed gözləntisi), %",
    "DEXCHUS": "Yuan / dollar məzənnəsi (Şanxay premiumu üçün)",
    "CFNAIMA3": "Çikaqo Fed milli fəallıq indeksi, 3 aylıq orta (iqtisadi böyümə)",
    "T10YIE": "10 illik inflyasiya gözləntisi, %",
    "DTWEXBGS": "Dollar indeksi (geniş)",
    "VIXCLS": "VIX qorxu indeksi",
    "GVZCLS": "Qızılın qorxu indeksi (GVZ: opsionların gözlədiyi tərpəniş), %",
    "SP500": "S&P 500 səhm indeksi",
    "DCOILWTICO": "Neft WTI (gündəlik), $",
}
SOURCE_IDS = ("rss", "forexfactory", "fred", "cot", "alpaca", "fmp", "official", "kalshi", "etf", "imf", "sge", "gld",
              "amfi", "geo")
# Block 9. Kalshi: market-implied odds of the next Fed decisions (public market data, no key).
KALSHI_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"
KALSHI_SERIES = ("KXFEDDECISION", "KXFED", "FEDDECISION", "FED")
# Intraday ETF proxies through the Alpaca key (IEX feed, US hours): gold and silver funds, miners, the dollar fund and
# Treasury funds (TIP = inflation-protected: an intraday stand-in for real yields, IEF = 7-10 year Treasuries).
ETF_SYMBOLS = ("GLD", "SLV", "GDX", "UUP", "TIP", "IEF")
ETF_URL = "https://data.alpaca.markets/v2/stocks/bars"
# CFTC Commitments of Traders (disaggregated, futures only; public, no key): weekly positions on COMEX / NYMEX.
COT_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
# Central banks' gold (IMF International Liquidity, «gold reserves, volume», fine troy ounces, monthly, free): the
# largest holders and the buyers of recent years. The fundamental block's FA-CB-1 rule reads their net purchases.
# SPDR Gold Trust (GLD, the largest gold ETF): the issuer's own daily archive since 2004 (XLSX), tonnes of gold held —
# the ETF flow. Used inside the system only (the file's terms forbid redistribution: nothing of it is republished).
GLD_URL = "https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en"
# AMFI (Association of Mutual Funds in India) monthly industry report: the official net inflow into India's gold ETFs
# (crore rupees). Owner's decision 2026-11-25. AMFI's terms allow personal, non-commercial use and forbid storing a
# significant portion of the site: only ONE number per month is kept (the gold ETF line), used inside the system only.
AMFI_URL = "https://portal.amfiindia.com/spages/am{mon}{year}repo.xls"
AMFI_FROM = (2019, 1)
# Shanghai Gold Exchange daily quotes (free): Au99.99 close in yuan per gram and its volume — China's physical demand.
SGE_URL = "https://en.sge.com.cn/data/data_daily_international_new"
IMF_URL = "https://api.imf.org/external/sdmx/2.1/data/IMF.STA,IL/{c}.RGV_REVS..M"
CB_COUNTRIES = ("CHN", "IND", "TUR", "POL", "RUS", "KAZ", "UZB", "CZE", "QAT", "SGP", "HUN", "THA", "IRQ", "JPN", "PHL",
                "EGY", "SAU", "BRA", "DEU", "FRA", "ITA", "NLD", "CHE", "GBR", "USA")
COT_CODES = {"088691": "XAU", "084691": "XAG", "076651": "XPT", "075651": "XPD"}
COT_EVERY = 12 * 3600
METAL_WORDS = {"XAU": r"\bgold\b|bullion", "XAG": r"\bsilver\b", "XPT": r"\bplatinum\b", "XPD": r"\bpalladium\b"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS news (uid TEXT PRIMARY KEY, source TEXT, url TEXT, title TEXT NOT NULL, ts REAL NOT NULL,
  metals TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS news_ts ON news(ts);
CREATE TABLE IF NOT EXISTS events (uid TEXT PRIMARY KEY, title TEXT, country TEXT, ts REAL, impact TEXT,
  forecast TEXT, previous TEXT, actual TEXT);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS macro (series TEXT NOT NULL, d TEXT NOT NULL, v REAL NOT NULL, PRIMARY KEY (series, d));
CREATE TABLE IF NOT EXISTS macro_first (series TEXT NOT NULL, d TEXT NOT NULL, v REAL NOT NULL, PRIMARY KEY (series, d));
CREATE TABLE IF NOT EXISTS cot (symbol TEXT NOT NULL, d TEXT NOT NULL, oi REAL, mm_long REAL, mm_short REAL,
  pm_long REAL, pm_short REAL, PRIMARY KEY (symbol, d));
"""


# ---------- parsers ----------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el, name):
    return next((c for c in el if _local(c.tag) == name), None)


def parse_date(raw: str) -> float | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def parse_feed(data: bytes, feed: str) -> list[dict]:
    """RSS 2.0 / Atom -> items {uid, source, url, title, ts, metals}. ValueError when it is not XML."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"XML deyil: {e}") from e
    out = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        t = _child(el, "title")
        title = (t.text or "").strip() if t is not None else ""
        ts = None
        for name in ("pubDate", "published", "updated", "date"):
            c = _child(el, name)
            if c is not None and c.text:
                ts = parse_date(c.text)
                if ts:
                    break
        if not title or ts is None:
            continue
        src = _child(el, "source")
        publisher = (src.text or "").strip() if src is not None and src.text else ""
        if publisher and title.endswith(" - " + publisher):
            title = title[: -len(publisher) - 3].rstrip()
        link = _child(el, "link")
        url = (link.text or link.get("href") or "").strip() if link is not None else ""
        metals = [m for m, rx in METAL_WORDS.items() if re.search(rx, title, re.I)]
        key = norm_title(title)
        if not key:
            continue
        out.append({"uid": hashlib.sha1(key.encode()).hexdigest()[:20], "source": publisher or feed,
                    "url": url if url.startswith(("http://", "https://")) else "", "title": title[:300], "ts": ts,
                    "metals": ",".join(metals)})
    return out


def parse_ff(data) -> list[dict]:
    """Forex Factory export -> events. A bare date or naive time is New York local, like the export."""
    if isinstance(data, (bytes, str)):
        data = json.loads(data)
    if not isinstance(data, list):
        raise ValueError("JSON siyahı gözlənilirdi")
    rows = []
    for ev in data:
        if not isinstance(ev, dict):
            continue
        title, raw = str(ev.get("title") or "").strip(), str(ev.get("date") or "").strip()
        if not title or not raw:
            continue
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=NY)
        country = str(ev.get("country") or "").upper()
        opt = lambda k: (str(ev.get(k)).strip() or None) if ev.get(k) not in (None, "") else None  # noqa: E731
        rows.append({"uid": hashlib.sha1(f"{country}|{title}|{raw}".encode()).hexdigest()[:20], "title": title,
                     "country": country, "ts": d.timestamp(), "impact": str(ev.get("impact") or "").title(),
                     "forecast": opt("forecast"), "previous": opt("previous"), "actual": opt("actual")})
    return rows


def parse_fred(data) -> list[tuple[str, float]]:
    if isinstance(data, (bytes, str)):
        data = json.loads(data)
    obs = data.get("observations") if isinstance(data, dict) else None
    if not isinstance(obs, list):
        raise ValueError(str(data.get("error_message") if isinstance(data, dict) else "cavab başa düşülmədi"))
    out = []
    for o in obs:
        try:
            out.append((o["date"], float(o["value"])))
        except (KeyError, TypeError, ValueError):
            continue   # "." = no value that day
    return out


AMFI_SCHEMA = "CREATE TABLE IF NOT EXISTS india_etf (month TEXT PRIMARY KEY, net REAL NOT NULL, known_ts REAL NOT NULL);"
MONTHS3 = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def _xlsx_rows(raw: bytes) -> list[list[list]]:
    """Every sheet of an .xlsx file (a zip of XML) as rows of cell values; no extra library."""
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(raw))
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(ns + "si"):
            shared.append("".join(t.text or "" for t in si.iter(ns + "t")))
    sheets = []
    for name in sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)):
        rows = []
        for row in ET.fromstring(z.read(name)).iter(ns + "row"):
            cells: dict[int, object] = {}
            for c in row.iter(ns + "c"):
                ref = re.match(r"([A-Z]+)", c.get("r", "A"))
                col = 0
                for ch in ref.group(1):
                    col = col * 26 + ord(ch) - 64
                v = c.find(ns + "v")
                if c.get("t") == "s" and v is not None:
                    val = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(ns + "t"))
                else:
                    val = v.text if v is not None else ""
                    try:
                        val = float(val)
                    except (TypeError, ValueError):
                        pass
                cells[col - 1] = val
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
        sheets.append(rows)
    return sheets


def parse_amfi_gold(raw: bytes) -> float | None:
    """AMFI's monthly report -> the gold ETF net inflow (+) / outflow (-) in crore rupees. Most months are old Excel
    (.xls); some are the newer .xlsx under the same .xls name (2026-11-25: April-June 2025 failed to read)."""
    if raw[:2] == b"PK":
        for rows in _xlsx_rows(raw):
            v = amfi_gold_from_rows(rows)
            if v is not None:
                return v
        return None
    import xlrd
    book = xlrd.open_workbook(file_contents=raw)
    for sh in book.sheets():
        v = amfi_gold_from_rows([[c.value for c in sh.row(r)] for r in range(sh.nrows)])
        if v is not None:
            return v
    return None


FOMC_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                           "september", "october", "november", "december"), 1)}


def parse_fomc(html: str) -> list[float]:
    """federalreserve.gov/monetarypolicy/fomccalendars.htm: per year a heading «2025 FOMC Meetings», then rows with
    the month (fomc-meeting__month) and the days (fomc-meeting__date, e.g. «28-29» or «29-30*»). The decision is
    announced at 14:00 New York on the last day. Returns those timestamps; [] if any year has fewer than 6."""
    import re
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    out, ok = [], True
    parts = re.split(r"(\d{4})\s+FOMC Meetings", html)
    for i in range(1, len(parts) - 1, 2):
        year, body = int(parts[i]), parts[i + 1]
        months = re.findall(r'fomc-meeting__month[^>]*>\s*(?:<[^>]+>\s*)*([A-Za-z/]+)', body)
        dates = re.findall(r'fomc-meeting__date[^>]*>\s*(?:<[^>]+>\s*)*([0-9][0-9\-–]*)', body)
        n = 0
        for mo, dd in zip(months, dates):
            mname = mo.split("/")[-1].lower()
            if mname not in FOMC_MONTHS:
                continue
            last = int(re.split(r"[-–]", dd)[-1])
            m = FOMC_MONTHS[mname]
            if "/" in mo and int(re.split(r"[-–]", dd)[0]) > last:
                pass                     # «Apr/May 30-1»: the decision day is in the second month
            try:
                out.append(datetime(year, m, last, 14, 0, tzinfo=ny).timestamp())
                n += 1
            except ValueError:
                continue
        if 2015 <= year <= 2100 and n < 6:
            ok = False
    return sorted(set(out)) if ok and out else []


def amfi_gold_from_rows(rows: list[list]) -> float | None:
    """The column whose header says «Net Inflow», on the row whose scheme name is «Gold ETF»."""
    col = None
    for cells in rows:
        txt = [str(x).strip() for x in cells]
        if col is None:
            col = next((i for i, x in enumerate(txt) if "net inflow" in x.lower()), None)
            continue
        if any(x.lower().startswith("gold etf") for x in txt[:3]) and col < len(cells):
            try:
                return round(float(cells[col]), 2)
            except (TypeError, ValueError):
                return None
    return None


def parse_gld_xlsx(raw: bytes) -> list[tuple[str, float]]:
    """GLD's archive (an XLSX: a zip of XML; no extra library) -> [(YYYY-MM-DD, tonnes)] in date order."""
    import zipfile
    from datetime import datetime as _dt
    z = zipfile.ZipFile(io.BytesIO(raw))
    strs = [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode(), re.S)]
    name = next((n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and
                 "Tonnes" in "".join(strs) and b"<row" in z.read(n)[:200000] and
                 len(re.findall(rb"<row ", z.read(n))) > 100), None)
    if not name:
        return []
    out = []
    head = None
    for row in re.findall(r"<row [^>]*>(.*?)</row>", z.read(name).decode(), re.S):
        cells = {}
        for c in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(?:<f>.*?</f>)?(?:<v>([^<]*)</v>)?)', row):
            v = c.group(3)
            if v is not None and 't="s"' in c.group(2):
                v = strs[int(v)]
            cells[c.group(1)] = v
        if head is None:
            if "Date" in cells.values():
                head = {v: k for k, v in cells.items() if v}
            continue
        try:
            d = _dt.strptime(cells.get(head["Date"], ""), "%d-%b-%Y").strftime("%Y-%m-%d")
            out.append((d, float(cells.get(head["Tonnes of Gold"], ""))))
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(out)


def parse_sge(text: str) -> list[tuple[str, float, float]]:
    """The SGE daily table -> (date, Au99.99 close yuan/g, volume kg)."""
    import html as _html
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        cells = [re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", c))).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
        if len(cells) >= 11 and cells[2] == "Au99.99":
            try:
                out.append((cells[1], float(cells[6].replace(",", "")), float(cells[10].replace(",", ""))))
            except ValueError:
                continue
    return out


def kalshi_prob(m: dict) -> float | None:
    """A Kalshi market's implied probability: the last trade, else the middle of bid and ask. Kalshi sends prices in
    cents (last_price: 45) or, in newer replies, in dollars as text (last_price_dollars: "0.4500")."""
    def val(key):
        if m.get(key + "_dollars") not in (None, ""):
            try:
                return float(m[key + "_dollars"])
            except (TypeError, ValueError):
                return None
        if m.get(key) is not None:
            try:
                return float(m[key]) / 100
            except (TypeError, ValueError):
                return None
        return None
    last = val("last_price")
    if last and 0 < last < 1:
        return round(last, 4)
    bid, ask = val("yes_bid"), val("yes_ask")
    if bid is not None and ask and 0 <= bid <= ask <= 1 and ask > 0:
        return round((bid + ask) / 2, 4)
    return None


def parse_cot(data) -> list[tuple]:
    """Socrata rows -> (symbol, date, open interest, managed money long, short, producer long, short)."""
    rows = json.loads(data) if isinstance(data, (bytes, str)) else data
    if not isinstance(rows, list):
        raise ValueError("COT: gözlənilməyən cavab")
    out = []
    for r in rows:
        sym = COT_CODES.get(str(r.get("cftc_contract_market_code", "")).strip())
        d = str(r.get("report_date_as_yyyy_mm_dd", ""))[:10]
        try:
            vals = [float(r[k]) for k in ("open_interest_all", "m_money_positions_long_all",
                                           "m_money_positions_short_all", "prod_merc_positions_long",
                                           "prod_merc_positions_short")]
        except (KeyError, TypeError, ValueError):
            continue
        if sym and len(d) == 10:
            out.append((sym, d, *vals))
    if rows and not out:
        raise ValueError("COT: sahə adları gözləniləndən fərqlidir: " + ", ".join(sorted(rows[0])[:12]))
    return out


def parse_alpaca(data) -> list[dict]:
    j = json.loads(data) if isinstance(data, (bytes, str)) else data
    if not isinstance(j, dict) or not isinstance(j.get("news"), list):
        raise ValueError("Alpaca: gözlənilməyən cavab")
    out = []
    for n in j["news"]:
        title = str(n.get("headline") or "").strip()
        if not title:
            continue
        try:
            ts = datetime.fromisoformat(str(n.get("created_at", "")).replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        metals = {ALPACA_SYMBOLS[s] for s in (n.get("symbols") or []) if s in ALPACA_SYMBOLS}
        text = (title + " " + str(n.get("summary") or "")).lower()
        metals |= {m for m, rx in METAL_WORDS.items() if re.search(rx, text)}
        url = str(n.get("url") or "")
        out.append({"uid": "alp:" + str(n.get("id")), "source": "Benzinga (Alpaca)",
                    "url": url if url.startswith(("http://", "https://")) else "", "title": title[:300], "ts": ts,
                    "metals": ",".join(sorted(metals))})
    return out


# ---------- the hub ----------
class Feeds:
    def __init__(self, db: DB, keys: KeyStore):
        self.db = db
        self.keys = keys
        db.script(SCHEMA)
        self.next_run = {"news": 0.0, "calendar": 0.0, "macro": 0.0, "cot": 0.0, "alpaca": 0.0, "fmp": 0.0,
                         "official": 0.0, "kalshi": 0.0, "etf": 0.0, "imf": 0.0, "sge": 0.0, "gld": 0.0, "amfi": 0.0, "geo": 0.0}
        self.activity = None      # app.activity.Hub: where each collector reports its status
        db.script(surprise.SCHEMA)

    def _health(self, sid: str, ok: bool | None, msg: str, rows: int = 0) -> None:
        """ok True: works; False: an error to fix; None: deliberately not used (shown grey, not as a problem)."""
        prev = json.loads(self.db.get(f"src:{sid}") or "{}")
        now = time.time()
        h = {**prev, "checked": now, "message": msg[:300], "rows": rows, "off": ok is None}
        if ok is None:
            h["ok"] = None
        elif ok:
            h["ok_ts"] = now
            h["ok"] = True
        else:
            h["ok"] = False
        self.db.put(f"src:{sid}", json.dumps(h))

    def health(self, sid: str) -> dict:
        return json.loads(self.db.get(f"src:{sid}") or "{}")

    async def _get(self, client: httpx.AsyncClient, url: str, headers: dict | None = None, **kw) -> bytes:
        r = await client.get(url, headers={**UA, **(headers or {})}, **kw)
        if r.status_code != 200:
            raise ValueError(f"HTTP {r.status_code}")
        if len(r.content) > MAX_BYTES:
            raise ValueError("cavab çox böyükdür")
        return r.content

    async def news(self, client) -> None:
        now, total, errors = time.time(), 0, []
        for name, url in NEWS_FEEDS:
            try:
                items = [i for i in parse_feed(await self._get(client, url), name) if now - i["ts"] < NEWS_MAX_AGE]
                self.db.executemany("INSERT OR IGNORE INTO news(uid, source, url, title, ts, metals) "
                                    "VALUES(:uid, :source, :url, :title, :ts, :metals)", items)
                total += len(items)
            except Exception as e:   # one feed failing must not cost the others
                errors.append(f"{name}: {e}")
        self.db.execute("DELETE FROM news WHERE ts < ?", (now - NEWS_KEEP,))
        ok = len(errors) < len(NEWS_FEEDS)
        self._health("rss", ok, f"{total} başlıq" + (f"; xəta: {'; '.join(errors)}" if errors else ""), total)
        from . import heartbeat              # the outside watcher: news is «down» after 3 failed rounds in a row
        bad = 0 if ok else int(self.db.get("hc:news_bad") or 0) + 1
        self.db.put("hc:news_bad", str(bad))
        if bad == 0:
            heartbeat.beat("news-agents", "ok", f"{total} başlıq")
        elif bad >= 3:
            heartbeat.beat("news-agents", "fail", f"{bad} dövr ardıcıl xəta")

    async def calendar(self, client) -> None:
        rows, errors = [], []
        for url in CAL_URLS:
            try:
                rows += parse_ff(await self._get(client, url))
            except Exception as e:
                # Next week's file is published late in the week: until then 404 is normal, not an error.
                if not (url.endswith("nextweek.json") and "404" in str(e)):
                    errors.append(str(e))
        if rows:
            self.db.executemany(
                "INSERT INTO events(uid, title, country, ts, impact, forecast, previous, actual) "
                "VALUES(:uid, :title, :country, :ts, :impact, :forecast, :previous, :actual) ON CONFLICT(uid) DO "
                "UPDATE SET forecast=excluded.forecast, previous=excluded.previous, actual=excluded.actual, "
                "impact=excluded.impact", rows)
        self._health("forexfactory", bool(rows), f"{len(rows)} hadisə" + (f"; xəta: {'; '.join(errors)}" if errors else ""),
                     len(rows))

    async def macro(self, client) -> None:
        key = self.keys.first("fred")
        if not key:
            self._health("fred", False, "FRED açarı saxlanmayıb")
            return
        n, errors = 0, []
        for sid in MACRO_SERIES:
            try:
                data = await self._get(client, "https://api.stlouisfed.org/fred/series/observations",
                                       params={"series_id": sid, "api_key": key, "file_type": "json",
                                               "sort_order": "desc", "limit": 3000})
                obs = parse_fred(data)
                self.db.executemany("INSERT OR REPLACE INTO macro(series, d, v) VALUES(?,?,?)",
                                    [(sid, d, v) for d, v in obs])
                n += len(obs)
            except Exception as e:
                errors.append(f"{sid}: {str(e).replace(key, '***')}")
        self._health("fred", n > 0, f"{n} müşahidə" + (f"; xəta: {'; '.join(errors)}" if errors else ""), n)
        await self.first_releases(client, key)
        await self.release_dates(client, key)
        await self.fomc_dates(client)
        if not getattr(self, "_geo_busy", False):     # in the background: the history takes a minute (5 s per call)
            self._geo_busy = True
            asyncio.get_running_loop().create_task(self._geo_bg())
        await self.event_firsts(client, key)

    async def fomc_dates(self, client) -> None:
        """The Fed's own meeting calendar (federalreserve.gov, US government, public): the decision days of the last
        years and the coming ones, for the conductor's «event» state. Once a day. If the page does not look as
        expected (fewer than 6 meetings a year), nothing is stored."""
        if time.time() - float(self.db.get("calendar:fomc_ts") or 0) < 86400:
            return
        self.db.put("calendar:fomc_ts", str(time.time()))
        try:
            r = await client.get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", timeout=30)
            days = parse_fomc(r.text) if r.status_code == 200 else []
            if days:
                hist = json.loads(self.db.get("calendar:history") or "{}")
                hist["FOMC"] = days
                self.db.put("calendar:history", json.dumps(hist))
            else:
                log.warning("fomc calendar: page not as expected (HTTP %s)", r.status_code)
        except Exception as e:
            log.warning("fomc calendar: %s", type(e).__name__)

    # FRED release ids of the US figures that move gold most (CPI, payrolls, GDP, PCE), all at 08:30 New York
    RELEASES = {10: "CPI", 50: "Employment Situation", 53: "GDP", 54: "Personal Income and Outlays"}

    async def release_dates(self, client, key: str) -> None:
        """The past dates of the big US releases (the conductor's «event» state needs them for the history, the
        calendar table only reaches a few days back). Once a day; stored as timestamps in kv «calendar:history»."""
        if time.time() - float(self.db.get("calendar:history_ts2") or 0) < 86400:
            return
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
        out: dict[str, list[float]] = {}
        errors = []
        for rid, name in self.RELEASES.items():
            try:
                data = await self._get(client, "https://api.stlouisfed.org/fred/release/dates",
                                       params={"release_id": rid, "api_key": key, "file_type": "json",
                                               "include_release_dates_with_no_data": "false",
                                               "sort_order": "asc", "limit": 10000})
                if isinstance(data, (bytes, str)):    # _get returns the raw body (2026-11-26: read as a dict, failed)
                    data = json.loads(data)
                if not isinstance(data, dict) or "release_dates" not in data:
                    raise ValueError(str(data.get("error_message") if isinstance(data, dict) else "cavab başa düşülmədi"))
                ts = []
                for r in data.get("release_dates", []):
                    d = datetime.strptime(r["date"], "%Y-%m-%d")
                    if d.year >= 2010:
                        ts.append(datetime(d.year, d.month, d.day, 8, 30, tzinfo=ny).timestamp())
                out[name] = ts
            except Exception as e:
                errors.append(f"{name}: {str(e).replace(key, '***')}"[:120])
        if out:
            hist = json.loads(self.db.get("calendar:history") or "{}")
            hist.update(out)                           # keep the FOMC days stored by fomc_dates
            self.db.put("calendar:history", json.dumps(hist))
        self.db.put("calendar:history_ts2", str(time.time()))
        if errors:
            log.warning("release dates: %s", "; ".join(errors))

    FIRST_SERIES = ("DTWEXBGS",)            # the revisable series the history replay reads (DFII10 is not revised)

    async def first_releases(self, client, key: str) -> None:
        """Arxivçi (Block 18): ALFRED's «initial release only» values — what was first published for each day, before
        later revisions — so the history replay never uses a figure that was not known yet. Once a day."""
        if time.time() - float(self.db.get("alfred:ts") or 0) < 86400:
            return
        got, errors = 0, []
        for sid in self.FIRST_SERIES:
            try:
                data = await self._get(client, "https://api.stlouisfed.org/fred/series/observations",
                                       params={"series_id": sid, "api_key": key, "file_type": "json",
                                               "output_type": 4, "realtime_start": "1776-07-04",
                                               "realtime_end": "9999-12-31"})
                obs = parse_fred(data)
                self.db.executemany("INSERT OR REPLACE INTO macro_first(series, d, v) VALUES(?,?,?)",
                                    [(sid, d, v) for d, v in obs])
                got += len(obs)
            except Exception as e:
                errors.append(f"{sid}: {str(e).replace(key, '***')}"[:120])
        self.db.put("alfred:ts", str(time.time()))
        self.db.put("alfred:last", json.dumps({"ts": time.time(), "n": got, "errors": errors}, ensure_ascii=False))
        if self.activity is not None:
            self.activity.report("archivist", "done" if got else "error",
                                 note=f"ALFRED ilk dərc: {got} dəyər" + (f"; xəta: {errors[0]}" if errors else ""))

    async def _geo_bg(self) -> None:
        from . import eventlib
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                new = await self.geo_volume(client)
            if new:                                  # new history years: rebuild the library now
                await asyncio.to_thread(eventlib.build, self.db)
        except Exception as e:
            log.warning("gdelt: %s", type(e).__name__)
        finally:
            self._geo_busy = False

    async def geo_volume(self, client, now: float | None = None) -> bool:
        """Hadisələr kitabxanası, geopolitics: GDELT's daily share of world news about war and military strikes (open
        data, no key). First the history from 2017 a year per request (GDELT asks for one request per 5 seconds),
        then the last three weeks each run."""
        from . import eventlib
        now = time.time() if now is None else now
        eventlib.ensure(self.db)
        have = {r["d"][:4] for r in self.db.execute("SELECT d FROM geo_vol").fetchall()}
        year = datetime.fromtimestamp(now, timezone.utc).year
        spans = [(f"{y}0101000000", f"{y}1231235959") for y in range(eventlib.GDELT_FROM, year)
                 if str(y) not in have]
        start = datetime.fromtimestamp(now - 21 * 86400, timezone.utc).strftime("%Y%m%d000000")
        spans.append((start, datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%d%H%M%S")))
        got, errors = 0, []
        for i, (a, b) in enumerate(spans):
            if i:
                await asyncio.sleep(6)
            try:
                r = await client.get(eventlib.GDELT_URL, params={"query": eventlib.GDELT_QUERY, "mode": "timelinevol",
                                                                 "format": "json", "startdatetime": a,
                                                                 "enddatetime": b, "timelinesmooth": 0},
                                     headers=UA, timeout=60)
                if r.status_code != 200:
                    raise ValueError(f"HTTP {r.status_code}")
                days = eventlib.parse_gdelt(r.text)
                today = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
                rows = [(d, v) for d, v in days.items() if d < today]      # only finished days
                self.db.executemany("INSERT OR REPLACE INTO geo_vol(d, v) VALUES(?,?)", rows)
                got += len(rows)
            except Exception as e:
                errors.append(f"{a[:8]}: {type(e).__name__} {str(e)[:80]}")
        self.db.put("eventlib:geo_fetch", json.dumps({"ts": now, "days": got, "errors": errors[:5]},
                                                     ensure_ascii=False))
        if errors:
            log.warning("gdelt: %s", "; ".join(errors[:3]))
        return len(spans) > 1 and got > 0

    async def event_firsts(self, client, key: str) -> None:
        """Hadisələr kitabxanası (app/eventlib.py): ALFRED's first published CPI, payrolls, PCE prices, real GDP and
        the Fed's upper target, then the library is rebuilt. Once a day (its own clock, so a new series does not wait
        for the archivist's)."""
        from . import eventlib
        if time.time() - float(self.db.get("eventlib:ts") or 0) < 86400 and self.db.get("eventlib:ver") == eventlib.EV_VER:
            return
        self.db.put("eventlib:ts", str(time.time()))
        got, errors = 0, []
        for sid in eventlib.FIRST_SERIES:
            try:
                params = {"series_id": sid, "api_key": key, "file_type": "json", "observation_start": "2005-01-01"}
                if sid not in eventlib.NOT_REVISED:     # the Fed's target is never revised: plain observations
                    params.update({"output_type": 4, "realtime_start": "1776-07-04", "realtime_end": "9999-12-31"})
                data = await self._get(client, "https://api.stlouisfed.org/fred/series/observations", params=params)
                obs = parse_fred(data)
                self.db.executemany("INSERT OR REPLACE INTO macro_first(series, d, v) VALUES(?,?,?)",
                                    [(sid, d, v) for d, v in obs])
                got += len(obs)
            except Exception as e:
                errors.append(f"{sid}: {str(e).replace(key, '***')}"[:120])
        self.db.put("eventlib:fetch", json.dumps({"ts": time.time(), "n": got, "errors": errors}, ensure_ascii=False))
        try:
            res = await asyncio.to_thread(eventlib.build, self.db)
            self.db.put("eventlib:ver", eventlib.EV_VER)
            note = f"kitabxana: {res['events']} hadisə, {res['moves']} hərəkət"
        except Exception as e:
            log.warning("eventlib: %s", e)
            note = f"kitabxana qurulmadı: {type(e).__name__}"
        if errors:
            log.warning("event firsts: %s", "; ".join(errors))
        if self.activity is not None:
            self.activity.report("archivist", "done" if got else "error",
                                 note=f"ALFRED (hadisələr): {got} dəyər; {note}" + (f"; xəta: {errors[0]}" if errors else ""))

    def _recent_release(self, now: float) -> bool:
        return self.db.execute("SELECT 1 FROM events WHERE country='USD' AND impact IN ('High','Medium') AND ts BETWEEN "
                               "? AND ?", (now - 2400, now + 60)).fetchone() is not None

    async def official(self, client) -> None:
        """US release actuals straight from BLS / FRED for releases of the last 3 days that have no actual yet."""
        from . import official as off, surprise
        surprise.ensure(self.db)
        now = time.time()
        due = []
        for r in self.db.execute("SELECT title, ts, impact, forecast FROM events WHERE country='USD' AND impact IN "
                                 "('High','Medium') AND ts BETWEEN ? AND ? AND forecast IS NOT NULL",
                                 (now - 3 * 86400, now - 30)).fetchall():
            p = off.plan(r["title"])
            uid = off.uid_of(r["title"], r["ts"])
            if p and not self.db.execute("SELECT 1 FROM releases WHERE uid=? AND actual IS NOT NULL", (uid,)).fetchone():
                due.append((dict(r), p, uid))
        if not due:
            self._health("official", True, "gözlənilən rəsmi rəqəm yoxdur", 0)
            return
        series: dict[str, list] = {}
        errors = []
        bls = sorted({p[1] for _, p, _ in due if p[0] == "bls"})
        if bls:
            year = datetime.now(timezone.utc).year
            body = {"seriesid": bls, "startyear": str(year - 1), "endyear": str(year)}
            if self.keys.first("bls"):
                body["registrationkey"] = self.keys.first("bls")
            try:
                rr = await client.post("https://api.bls.gov/publicAPI/v2/timeseries/data/", json=body, headers=UA)
                series.update(off.parse_bls(rr.json()))
            except Exception as e:
                errors.append(f"BLS: {e}"[:120])
        fred_key = self.keys.first("fred")
        for sid in sorted({p[1] for _, p, _ in due if p[0] == "fred"}):
            if not fred_key:
                errors.append("FRED açarı yoxdur")
                break
            try:
                data = await self._get(client, "https://api.stlouisfed.org/fred/series/observations",
                                       params={"series_id": sid, "api_key": fred_key, "file_type": "json",
                                               "sort_order": "desc", "limit": 15})
                series[sid] = sorted((d, v) for d, v in parse_fred(data))
            except Exception as e:
                errors.append(f"{sid}: {str(e).replace(fred_key, '***')}"[:120])
        found = 0
        for ev, (src, sid, unit), uid in due:
            res = off.compute(unit, series.get(sid, []))
            if not res or not off.period_ok(unit, sid, res[0], ev["ts"]):
                continue                                   # the agency has not published this period yet
            surprise.store(self.db, [{"uid": uid, "ts": ev["ts"], "event": ev["title"], "impact": ev["impact"],
                                      "estimate": surprise._num(ev["forecast"]), "previous": None, "actual": res[1],
                                      "raw_date": datetime.fromtimestamp(ev["ts"], timezone.utc).strftime(
                                          "%Y-%m-%d %H:%M:%S"), "known_ts": now}])
            found += 1
        self._health("official", not errors, f"{found}/{len(due)} rəsmi rəqəm" +
                     (f"; xəta: {'; '.join(errors)}" if errors else ""), found)

    async def gld(self, client) -> None:
        """GLD's holdings (tonnes) per day from the issuer's archive, every six hours."""
        self.db.script("CREATE TABLE IF NOT EXISTS etf_gold (fund TEXT, d TEXT, tonnes REAL, PRIMARY KEY (fund, d));")
        try:
            r = await client.get(GLD_URL, headers=UA)
            if r.status_code != 200:
                raise ValueError(f"HTTP {r.status_code}")
            rows = parse_gld_xlsx(r.content)
            self.db.executemany("INSERT OR REPLACE INTO etf_gold VALUES('GLD',?,?)", rows)
            self._health("gld", bool(rows), f"GLD: {len(rows)} gün, son {rows[-1][0]} = {rows[-1][1]:.1f} ton"
                         if rows else "GLD faylında sətir yoxdur", len(rows))
        except Exception as e:
            self._health("gld", False, f"GLD: {str(e)[:120]}")

    async def geo(self, client) -> None:
        """DB-IP's free city database for the security journal's places, refreshed once a month (read locally only)."""
        from . import geo
        try:
            msg = await geo.refresh(client, self.db.path)
            self._health("geo", True, f"DB-IP şəhər bazası: {msg} (ünvanlar heç yerə göndərilmir)", 1)
        except Exception as e:
            self._health("geo", False, f"DB-IP: {str(e)[:120]}")

    async def amfi(self, client, now: float | None = None) -> None:
        """India's gold ETF net flow per month from AMFI's official report: the newest months every six hours (the
        report appears around the 10th), the history since 2019 twelve files per run (gentle on the site)."""
        now = time.time() if now is None else now
        self.db.script(AMFI_SCHEMA)
        have = {r["month"] for r in self.db.execute("SELECT month FROM india_etf").fetchall()}
        d = datetime.fromtimestamp(now, timezone.utc)
        months, y, m = [], d.year, d.month
        while (y, m) >= AMFI_FROM:
            m -= 1
            if m == 0:
                y, m = y - 1, 12
            if (y, m) >= AMFI_FROM:
                months.append((y, m))
        todo = [x for x in months[:2] if f"{x[0]}-{x[1]:02d}" not in have] + \
            [x for x in months[2:] if f"{x[0]}-{x[1]:02d}" not in have][:12]
        got, errors = 0, []
        for y, m in todo:
            url = AMFI_URL.format(mon=MONTHS3[m - 1], year=y)
            try:
                r = await client.get(url, headers=UA)
                if r.status_code == 404:
                    continue                                  # not published yet (or no xls that month)
                if r.status_code != 200:
                    raise ValueError(f"HTTP {r.status_code}")
                net = parse_amfi_gold(r.content)
                if net is None:
                    errors.append(f"{y}-{m:02d}: qızıl ETF sətri tapılmadı")
                    continue
                ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
                public = datetime(ny, nm, 15, tzinfo=timezone.utc).timestamp()     # AMFI publishes by ~the 12th
                self.db.execute("INSERT OR IGNORE INTO india_etf VALUES(?,?,?)", (f"{y}-{m:02d}", net, min(now, public)))
                got += 1
            except Exception as e:
                errors.append(f"{y}-{m:02d}: {str(e)[:80]}")
        last = self.db.execute("SELECT month, net FROM india_etf ORDER BY month DESC LIMIT 1").fetchone()
        n = self.db.execute("SELECT COUNT(*) n FROM india_etf").fetchone()["n"]
        self._health("amfi", not errors and n > 0, f"AMFI: {n} ay" + (f", son {last['month']} = {last['net']:+,.0f} krore"
                                                                       if last else "") +
                     (f"; xəta: {'; '.join(errors[:3])}" if errors else ""), n)

    async def sge(self, client) -> None:
        """Shanghai Gold Exchange: Au99.99 daily close (yuan/gram) and volume (kg). The site's table shows about one
        day per page, so each day is asked on its own: the last ten days every run, and the two-year history filled
        in 60 days per hourly run (gentle on the site; complete in about ten hours)."""
        self.db.script("CREATE TABLE IF NOT EXISTS sge_gold (d TEXT PRIMARY KEY, close REAL, volume_kg REAL);")
        from datetime import date, timedelta
        have = {r["d"] for r in self.db.execute("SELECT d FROM sge_gold").fetchall()}
        tried = set(json.loads(self.db.get("sge:empty") or "[]"))          # holidays and weekends: asked once
        today = date.today()
        days = [today - timedelta(days=k) for k in range(10)]
        back = [today - timedelta(days=k) for k in range(10, 730)]
        days += [d for d in back if d.isoformat() not in have and d.isoformat() not in tried and d.weekday() < 5][:60]
        got, errors = 0, []
        for d in days:
            if d.isoformat() in have and d < today - timedelta(days=3):
                continue
            try:
                raw = await self._get(client, SGE_URL, params={"start_date": d.isoformat(), "end_date": d.isoformat()})
                rows = parse_sge(raw.decode("utf-8", "replace"))
                if rows:
                    self.db.executemany("INSERT OR REPLACE INTO sge_gold VALUES(?,?,?)", rows)
                    got += len(rows)
                elif d < today - timedelta(days=3):
                    tried.add(d.isoformat())
            except Exception as e:
                errors.append(f"{d}: {str(e)[:60]}")
        self.db.put("sge:empty", json.dumps(sorted(tried)[-800:]))
        n = self.db.execute("SELECT COUNT(*) n, MIN(d) a, MAX(d) b FROM sge_gold").fetchone()
        self._health("sge", n["n"] > 0, f"{n['n']} gün ({n['a']} – {n['b']})" +
                     (f"; xəta: {'; '.join(errors[:3])}" if errors else ""), got)

    async def imf_gold(self, client) -> None:
        """Central banks' gold holdings (IMF), once a day: the monthly volume per country since 2014."""
        import csv
        self.db.script("CREATE TABLE IF NOT EXISTS cb_gold (country TEXT, period TEXT, oz REAL, PRIMARY KEY (country, period));")
        try:
            raw = await self._get(client, IMF_URL.format(c="+".join(CB_COUNTRIES)),
                                  headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"},
                                  params={"startPeriod": "2014-01", "detail": "dataonly"})
            rows = []
            for r in csv.DictReader(io.StringIO(raw.decode("utf-8", "replace"))):
                per, v = r.get("TIME_PERIOD", ""), r.get("OBS_VALUE", "")
                if len(per) == 8 and per[4:6] == "-M" and v:
                    rows.append((r.get("COUNTRY", ""), per[:4] + "-" + per[6:], float(v)))
            self.db.executemany("INSERT OR REPLACE INTO cb_gold VALUES(?,?,?)", rows)
            last = max((p for _, p, _ in rows), default="—")
            self._health("imf", bool(rows), f"{len(rows)} aylıq qeyd, {len({c for c, _, _ in rows})} mərkəzi bank, "
                                            f"son ay {last}", len(rows))
        except Exception as e:
            self._health("imf", False, f"IMF: {str(e)[:120]}")

    async def kalshi(self, client) -> None:
        """Market-implied odds of the next Fed decisions: each open market's last price (cents) = probability."""
        self.db.script("CREATE TABLE IF NOT EXISTS fed_odds (ts REAL, ticker TEXT, title TEXT, "
                                   "prob REAL, close_ts REAL, PRIMARY KEY (ticker, ts));")
        now = time.time()
        rows, errors = [], []
        seen = []
        for series in KALSHI_SERIES:
            try:
                data = json.loads(await self._get(client, KALSHI_URL, params={"series_ticker": series,
                                                                              "status": "open", "limit": 100}))
                markets = data.get("markets", [])
                if not markets:
                    # some series list their markets under events: ask the events endpoint with the markets nested
                    ev = json.loads(await self._get(client, KALSHI_URL.replace("/markets", "/events"), params={
                        "series_ticker": series, "status": "open", "with_nested_markets": "true", "limit": 50}))
                    markets = [m for e in ev.get("events", []) for m in (e.get("markets") or [])]
                    seen.append(f"{series}: {len(ev.get('events', []))} hadisə")
                else:
                    seen.append(f"{series}: {len(markets)} bazar")
                for m in markets:
                    prob = kalshi_prob(m)
                    if prob is None:
                        continue
                    close = m.get("close_time") or ""
                    try:
                        close_ts = datetime.fromisoformat(close.replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        close_ts = None
                    title = (m.get("title") or "") + (" — " + m["yes_sub_title"] if m.get("yes_sub_title") else "")
                    rows.append((now, m.get("ticker", ""), title[:200], prob, close_ts))
            except Exception as e:
                errors.append(f"{series}: {e}"[:120])
        if rows:
            self.db.executemany("INSERT OR REPLACE INTO fed_odds VALUES(?,?,?,?,?)", rows)
            self.db.execute("DELETE FROM fed_odds WHERE ts < ?", (now - 30 * 86400,))
        self._health("kalshi", bool(rows), f"{len(rows)} Fed bazarı ({'; '.join(seen)})" +
                     (f"; xəta: {'; '.join(errors)}" if errors else ""), len(rows))

    def fed_odds(self, limit: int = 8) -> list[dict]:
        """The latest odds of the nearest Fed decision markets (for the brains' facts and the panel)."""
        try:
            last = self.db.execute("SELECT MAX(ts) FROM fed_odds").fetchone()[0]
        except Exception:
            return []
        if not last:
            return []
        return [dict(r) for r in self.db.execute(
            "SELECT title, prob, close_ts FROM fed_odds WHERE ts=? ORDER BY close_ts, prob DESC LIMIT ?",
            (last, limit)).fetchall()]

    async def etf(self, client) -> None:
        """15-minute bars of the ETF proxies into the candles table (symbols GLD, SLV, ...): the brains see their moves."""
        creds = self.keys.get("alpaca")
        if not creds:
            self._health("etf", False, "Alpaca açarı yoxdur")
            return
        from . import candles
        start = datetime.fromtimestamp(time.time() - 5 * 86400, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            data = json.loads(await self._get(client, ETF_URL, params={
                "symbols": ",".join(ETF_SYMBOLS), "timeframe": "15Min", "start": start, "feed": "iex", "limit": 10000},
                headers={"APCA-API-KEY-ID": creds.get("key_id", ""), "APCA-API-SECRET-KEY": creds.get("secret", "")}))
            n = 0
            for sym, bars in (data.get("bars") or {}).items():
                rows = []
                for b in bars:
                    t = int(datetime.fromisoformat(b["t"].replace("Z", "+00:00")).timestamp())
                    rows.append((t, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
                n += candles.store_history(self.db, sym, "15m", rows, replace=True)
            self._health("etf", n > 0, f"{n} şam ({', '.join(ETF_SYMBOLS)}; yalnız ABŞ saatları)", n)
        except Exception as e:
            msg = str(e)
            for v in creds.values():
                if v:
                    msg = msg.replace(v, "***")
            self._health("etf", False, f"ETF: {msg}"[:300])

    async def cot(self, client) -> None:
        codes = ",".join(f"'{c}'" for c in COT_CODES)
        data = await self._get(client, COT_URL, params={
            "$select": "cftc_contract_market_code,report_date_as_yyyy_mm_dd,open_interest_all,"
                       "m_money_positions_long_all,m_money_positions_short_all,prod_merc_positions_long,"
                       "prod_merc_positions_short",
            "$where": f"cftc_contract_market_code in({codes})", "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": str(len(COT_CODES) * 160)})
        rows = parse_cot(data)
        self.db.executemany("INSERT OR REPLACE INTO cot(symbol, d, oi, mm_long, mm_short, pm_long, pm_short) "
                            "VALUES(?,?,?,?,?,?,?)", rows)
        last = max((r[1] for r in rows), default="—")
        self._health("cot", bool(rows), f"{len(rows)} həftəlik hesabat, sonuncu {last}", len(rows))

    async def tick(self, now: float | None = None, force: str | None = None) -> None:
        now = time.time() if now is None else now
        jobs = {"news": (self.news, NEWS_EVERY), "calendar": (self.calendar, CAL_EVERY),
                "macro": (self.macro, MACRO_EVERY), "cot": (self._cot_safe, COT_EVERY),
                "alpaca": (self.alpaca, ALPACA_EVERY),
                # every 5 minutes; every minute around a high-impact release so the surprise is seen at once
                "fmp": (self.fmp, 60 if self.event_mode(now) else 300),
                # official actuals: every minute around a release (the agencies publish at the minute)
                "official": (self.official, 60 if self._recent_release(now) else 900),
                "kalshi": (self.kalshi, 900), "etf": (self.etf, 300), "imf": (self.imf_gold, 86400),
                "sge": (self.sge, 3600), "gld": (self.gld, 6 * 3600), "amfi": (self.amfi, 6 * 3600), "geo": (self.geo, 86400)}
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            for name, (fn, every) in jobs.items():
                if force == name or (force is None and now >= self.next_run[name]):
                    self.next_run[name] = now + every
                    task = {"news": "news", "alpaca": "news", "calendar": "calendar", "fmp": "calendar",
                            "macro": "macro", "cot": "macro", "official": "calendar", "kalshi": "macro",
                            "etf": "macro", "imf": "macro", "sge": "macro", "gld": "macro", "amfi": "macro", "geo": "macro"}[name]
                    if self.activity:
                        self.activity.report(task, "working", note=name)
                    try:
                        await fn(client)
                        if self.activity:
                            h = self.health({"news": "rss"}.get(name, {"calendar": "forexfactory", "macro": "fred"}
                                                                 .get(name, name)))
                            ok = h.get("ok") is not False
                            self.activity.report(task, "done" if ok else "error", note=f"{name}: {h.get('message', '')}"[:150])
                    except Exception as e:
                        log.exception("feed %s failed", name)
                        if self.activity:
                            self.activity.report(task, "error", note=f"{name}: {type(e).__name__}")

    async def alpaca(self, client) -> None:
        creds = self.keys.get("alpaca")
        if not creds:
            return
        try:
            data = await self._get(client, ALPACA_URL, params={"symbols": ",".join(ALPACA_SYMBOLS), "limit": "50",
                                                               "sort": "desc"},
                                   headers={**UA, "APCA-API-KEY-ID": creds.get("key_id", ""),
                                            "APCA-API-SECRET-KEY": creds.get("secret", "")})
            items = [i for i in parse_alpaca(data) if time.time() - i["ts"] < NEWS_MAX_AGE]
            self.db.executemany("INSERT OR IGNORE INTO news(uid, source, url, title, ts, metals) "
                                "VALUES(:uid, :source, :url, :title, :ts, :metals)", items)
            self._health("alpaca", True, f"{len(items)} başlıq (son 48 saat)", len(items))
        except Exception as e:
            msg = str(e)
            for v in creds.values():
                if v:
                    msg = msg.replace(v, "***")
            self._health("alpaca", False, f"Alpaca: {msg}"[:300])

    async def fmp(self, client) -> None:
        """US releases with estimate and actual (FMP). The first run also loads two years back, so the history
        replay can test the surprise method; then the last two days and the next week every few minutes."""
        key = self.keys.first("fmp")
        if not key:
            return
        today = datetime.now(timezone.utc).date()
        from datetime import timedelta
        spans = [(today - timedelta(days=2), today + timedelta(days=7))]
        if self.db.execute("SELECT COUNT(*) FROM releases").fetchone()[0] < 300:
            spans += [(today - timedelta(days=d + 89), today - timedelta(days=d)) for d in range(3, 731, 90)]
        n, errors = 0, []
        for a, b in spans:
            try:
                rows = surprise.parse_fmp(await self._get(client, surprise.FMP_URL,
                                                          params={"from": a.isoformat(), "to": b.isoformat(),
                                                                  "apikey": key}))
                surprise.store(self.db, rows)
                n += len(rows)
            except Exception as e:
                errors.append(str(e).replace(key, "***")[:120])
                if "HTTP 402" in str(e) or "HTTP 403" in str(e):
                    # The owner decided not to buy the calendar plan (2026-11-24): the actuals come from BLS / FRED.
                    # Not an error: the source is simply not used; asked again once a day in case the plan changes.
                    self.next_run["fmp"] = time.time() + 86400
                    self._health("fmp", None, "istifadə olunmur: FMP planında təqvim yoxdur. ABŞ rəqəmlərinin faktı "
                                              "rəsmi mənbələrdən (BLS, FRED) gəlir; plan alınsa, özü qoşulacaq.", 0)
                    return
                if "HTTP 4" in str(e):
                    break          # a bad key or request: asking again changes nothing
        last = self.db.execute("SELECT raw_date, event FROM releases WHERE actual IS NOT NULL AND impact='High' "
                               "ORDER BY ts DESC LIMIT 1").fetchone()
        msg = f"{n} ABŞ rəqəmi" + (f"; son açıqlanan: {last['event']} ({last['raw_date']} UTC)" if last else "")
        self._health("fmp", n > 0, msg + (f"; xəta: {'; '.join(errors)}" if errors else ""), n)

    async def _cot_safe(self, client) -> None:
        try:
            await self.cot(client)
        except Exception as e:
            self._health("cot", False, f"COT: {e}"[:300])

    # ---------- views ----------
    def cot_view(self) -> list[dict]:
        """Per metal: big funds' (managed money) net position, its share of open interest, the weekly change and
        where it stands in its 3-year range (0 % = most bearish in 3 years, 100 % = most bullish: crowded)."""
        out = []
        for sym in COT_CODES.values():
            rows = self.db.execute("SELECT d, oi, mm_long, mm_short FROM cot WHERE symbol=? ORDER BY d DESC LIMIT 156",
                                   (sym,)).fetchall()
            if not rows:
                out.append({"symbol": sym, "date": None})
                continue
            nets = [r["mm_long"] - r["mm_short"] for r in rows]
            lo, hi = min(nets), max(nets)
            out.append({"symbol": sym, "date": rows[0]["d"], "net": nets[0],
                        "net_pct_oi": nets[0] / rows[0]["oi"] * 100 if rows[0]["oi"] else None,
                        "change": nets[0] - nets[1] if len(nets) > 1 else None,
                        "rank": (nets[0] - lo) / (hi - lo) * 100 if hi > lo else None, "weeks": len(nets)})
        return out

    def latest_news(self, limit: int = 30, metal: str | None = None) -> list[dict]:
        sql, args = "SELECT uid, source, url, title, ts, metals FROM news", []
        if metal:
            sql += " WHERE metals LIKE ?"
            args.append(f"%{metal}%")
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def upcoming(self, now: float, days: float = 7, impacts=("High", "Medium")) -> list[dict]:
        rows = self.db.execute(
            f"SELECT title, country, ts, impact, forecast, previous, actual FROM events WHERE country='USD' AND "
            f"ts >= ? AND ts <= ? AND impact IN ({','.join('?' * len(impacts))}) ORDER BY ts",
            (now - 6 * 3600, now + days * 86400, *impacts)).fetchall()
        return [dict(r) for r in rows]

    def event_mode(self, now: float) -> dict | None:
        """A High-impact US release from 15 minutes before to 30 minutes after: forecasts give ranges only."""
        r = self.db.execute("SELECT title, ts FROM events WHERE country='USD' AND impact='High' AND ts BETWEEN ? AND ? "
                            "ORDER BY ts LIMIT 1", (now - 1800, now + 900)).fetchone()
        return dict(r) if r else None

    def macro_view(self) -> list[dict]:
        out = []
        for sid, name in MACRO_SERIES.items():
            rows = self.db.execute("SELECT d, v FROM macro WHERE series=? ORDER BY d DESC LIMIT 6", (sid,)).fetchall()
            if not rows:
                out.append({"series": sid, "name": name, "value": None})
                continue
            last, week = rows[0], rows[min(5, len(rows) - 1)]
            out.append({"series": sid, "name": name, "value": last["v"], "date": last["d"],
                        "change_week": last["v"] - week["v"], "since": week["d"]})
        return out
