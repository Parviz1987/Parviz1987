"""Free data collectors: news headlines (RSS, no key), the US economic calendar (Forex Factory export, no key) and
macro series from FRED (free key). Parsers adapted from pj-trade-gold (app/news.py, app/econcal.py).

Each source keeps its health in kv "src:<id>" (last success, last error, rows), so the panel shows what works.
Nothing here is a price: prices come only from the price provider."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import httpx

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
    "T10YIE": "10 illik inflyasiya gözləntisi, %",
    "DTWEXBGS": "Dollar indeksi (geniş)",
    "VIXCLS": "VIX qorxu indeksi",
    "SP500": "S&P 500 səhm indeksi",
}
# CFTC Commitments of Traders (disaggregated, futures only; public, no key): weekly positions on COMEX / NYMEX.
COT_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
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
        db.conn.executescript(SCHEMA)
        self.next_run = {"news": 0.0, "calendar": 0.0, "macro": 0.0, "cot": 0.0, "alpaca": 0.0}

    def _health(self, sid: str, ok: bool, msg: str, rows: int = 0) -> None:
        prev = json.loads(self.db.get(f"src:{sid}") or "{}")
        now = time.time()
        h = {**prev, "checked": now, "message": msg[:300], "rows": rows}
        if ok:
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
                "alpaca": (self.alpaca, ALPACA_EVERY)}
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            for name, (fn, every) in jobs.items():
                if force == name or (force is None and now >= self.next_run[name]):
                    self.next_run[name] = now + every
                    try:
                        await fn(client)
                    except Exception:
                        log.exception("feed %s failed", name)

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
