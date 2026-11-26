"""Bazar müxbiri (owner 2026-11-25: «an agent that keeps bringing the data we cannot download: India, from the news»).

The physical market's weekly and monthly figures that no free official feed gives us, found in published news by two
brains from two companies independently (the Rəqəm ovçusu way): each figure must come with a source link, and it is
used only when both brains found the same figure for the same period. Nothing is estimated; no price comes from a
brain — only a number printed in a news report (premium in dollars per ounce, tonnes, rupees).

The data agents (Məlumat agentləri, owner 2026-11-26) are listed in TOPICS below with their days and hours: India
(IBJA daily rate, premium, imports, RBI gold), China (premium, PBoC gold), the world (WGC ETF flows, COMEX stocks), the
US (next FOMC date). India's gold ETF flow is not asked here: it comes from AMFI's official report (feeds.amfi).
Monthly limit: the slot «reporter» (10 $ a month, the owner's decision)."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

from . import brains
from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_reports (topic TEXT NOT NULL, period TEXT NOT NULL, value REAL, unit TEXT,
  ts REAL NOT NULL, a TEXT, b TEXT, accepted INTEGER NOT NULL, note TEXT, PRIMARY KEY (topic, period, ts));
"""
# Each data agent: what it looks for, when (weekdays, UTC hour), the unit, how close the two brains must agree
# (absolute, or relative with "rel"), its group on the page and what it feeds. Owner 2026-11-26: «build an agents
# block inside the news block: what we cannot download, our idle brains find on the internet» — only figures printed
# in news reports or official releases; never a site's members-only file or a page whose terms forbid automated use.
TOPICS = {
    "ibja_rate": {"days": (0, 1, 2, 3, 4), "hour": 8, "unit": "INR/10g", "tol": 0.002, "rel": True, "group": "Hindistan",
                  "name": "IBJA qızıl qiyməti (999, 10 qram)",
                  "q": "The India Bullion and Jewellers Association (IBJA) benchmark rate for 24-carat (999 purity) gold, "
                       "in Indian rupees per 10 grams, for today's date (or the latest trading day), as printed in a news "
                       "report (for example Economic Times, Business Standard, Moneycontrol). Use the opening/AM rate if "
                       "two are quoted. Do not read ibjarates.com itself."},
    "india_premium": {"days": (4, 0), "hour": 13, "unit": "$/oz", "tol": 2.0, "group": "Hindistan",
                      "name": "Hindistan premiumu / endirimi",
                      "q": "Indian gold dealers' premium (positive) or discount (negative) over official domestic "
                           "prices (which include import and sales taxes), as reported in the most recent weekly "
                           "report (for example Reuters 'Asia Gold'). In US dollars per ounce. If a range is quoted, "
                           "give the mid-point (e.g. a discount of $10-$20 is -15)."},
    "india_imports": {"days": (2,), "hour": 13, "unit": "tonnes", "tol": 0.10, "rel": True, "group": "Hindistan",
                      "name": "Hindistanın aylıq qızıl idxalı",
                      "q": "India's gold imports in the most recent month for which a figure has been published "
                           "(government data or a major news report), in metric tonnes."},
    "rbi_gold": {"days": (3,), "hour": 13, "unit": "tonnes", "tol": 0.01, "rel": True, "group": "Hindistan",
                 "name": "Hindistan Mərkəzi Bankının (RBI) qızılı",
                 "q": "The Reserve Bank of India's total gold reserves in metric tonnes, latest figure reported "
                      "(RBI release or a major news report), with the month or date it refers to."},
    "china_premium": {"days": (4, 0), "hour": 13, "unit": "$/oz", "tol": 3.0, "group": "Çin",
                      "name": "Çin premiumu",
                      "q": "Chinese gold dealers' premium (positive) or discount (negative) over the global benchmark "
                           "spot price, as reported in the most recent weekly report (for example Reuters 'Asia Gold'). "
                           "In US dollars per ounce; mid-point if a range is quoted."},
    "pboc_gold": {"days": (1, 4), "hour": 13, "unit": "mln oz", "tol": 0.001, "rel": True, "group": "Çin",
                  "name": "Çin Mərkəzi Bankının (PBoC) qızılı",
                  "q": "The People's Bank of China's official gold reserves at the end of the most recent month, in "
                       "million fine troy ounces, as published by the PBoC / SAFE or reported by Reuters or Bloomberg."},
    "wgc_etf": {"days": (1, 3), "hour": 14, "unit": "tonnes", "tol": 0.10, "rel": True, "group": "Dünya",
                "name": "Dünya qızıl ETF axını (aylıq, WGC)",
                "q": "Global gold ETF net flows in the most recent month in metric tonnes (positive = inflow), as "
                     "published by the World Gold Council in its public press release or as reported by news "
                     "(Reuters, Bloomberg, Kitco). Do not use members-only Goldhub downloads."},
    "comex_stocks": {"days": (2,), "hour": 22, "unit": "mln oz", "tol": 0.02, "rel": True, "group": "Dünya",
                     "name": "COMEX qızıl anbarı (registered + eligible)",
                     "q": "Total COMEX gold warehouse stocks (registered plus eligible) in million troy ounces, the "
                          "latest daily figure reported by CME Group or in a news report, with its date."},
    "fomc_next": {"days": (0,), "hour": 14, "unit": "tarix", "tol": 0.0, "group": "ABŞ",
                  "name": "Növbəti Fed (FOMC) qərar günü",
                  "q": "The date of the next scheduled FOMC (Federal Reserve) policy decision announcement after today, "
                       "from the Federal Reserve's published meeting calendar. Give value as a number YYYYMMDD and "
                       "period as YYYY-MM."},
}
SYSTEM = ("You look up published figures about the physical gold market on the web. Report only a figure you actually "
          "find printed in a news report or official release, for the exact item asked, with the period it refers "
          "to. Never estimate or compute it yourself. If you cannot find it, set found to false. Answer ONLY with one "
          'JSON object: {"found": true|false, "value": number, "unit": "...", "period": "the week ending YYYY-MM-DD '
          'or the month YYYY-MM the figure refers to", "source_url": "the page you read it on"}')
HOUR_UTC = 13          # the default hour; each agent has its own (IBJA in the Indian morning, COMEX after the close)


def ensure(db: DB) -> None:
    db.script(SCHEMA)


def _period(p: str | None) -> str | None:
    m = re.search(r"(\d{4})-(\d{2})(?:-(\d{2}))?", str(p or ""))
    if not m:
        return None
    return m.group(0)


def _agree(topic: str, a: float, b: float) -> bool:
    t = TOPICS[topic]
    if t.get("rel"):
        return abs(a - b) <= t["tol"] * max(abs(a), abs(b), 1e-9)
    return abs(a - b) <= t["tol"]


class Reporter:
    def __init__(self, db: DB, keys):
        self.db = db
        self.keys = keys
        ensure(db)
        self.activity = None

    def due(self, now: float) -> list[str]:
        d = datetime.fromtimestamp(now, timezone.utc)
        day = d.strftime("%Y-%m-%d")
        out = []
        for topic, t in TOPICS.items():
            if d.hour >= t.get("hour", HOUR_UTC) and d.weekday() in t["days"] and \
                    self.db.get(f"reporter:{topic}:day") != day and now >= float(self.db.get(f"reporter:{topic}:retry") or 0):
                out.append(topic)
        return out

    async def tick(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        due = self.due(now)
        if not due or not (self.keys.first("gemini") or self.keys.first("openai") or self.keys.first("anthropic")):
            return 0
        rep = self.activity.report if self.activity else (lambda *a, **k: None)
        day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
        found = 0
        for topic in due:
            self.db.put(f"reporter:{topic}:day", day)           # asked once a day, whatever the answer
            rep("reporter", "working", "W1 İki beyin axtarır", 0.3, topic)
            answers = await brains.run_both(self.db, self.keys, "reporter", SYSTEM,
                                            f"Find: {TOPICS[topic]['q']} Today is {day}.", max_tokens=1200)
            vals = []
            for data, how in answers:
                ok = isinstance(data, dict) and data.get("found") is True and \
                    str(data.get("source_url", "")).startswith(("https://", "http://"))
                try:
                    v = float(data.get("value")) if ok else None
                except (TypeError, ValueError):
                    v = None
                vals.append({"value": v, "period": _period(data.get("period")) if ok else None,
                             "url": str(data.get("source_url"))[:300] if ok else None, "brain": how})
            rep("reporter", "working", "W2 Müqayisə", 0.85, topic)
            # a brain that failed technically (a retired model, a timeout) does not use up the day: one more try in
            # two hours, at most three tries a day (2026-11-26: Gemini's retired model cost the day's IBJA figure)
            broken = sum(1 for data, how in answers if data is None)
            tries = int(self.db.get(f"reporter:{topic}:tries:{day}") or 0) + 1
            self.db.put(f"reporter:{topic}:tries:{day}", str(tries))
            if broken and tries < 3:
                self.db.delete(f"reporter:{topic}:day")
                self.db.put(f"reporter:{topic}:retry", str(now + 2 * 3600))
            a, b = (vals + [{}, {}])[:2]
            accepted = (a.get("value") is not None and b.get("value") is not None and a.get("period")
                        and a.get("period") == b.get("period") and _agree(topic, a["value"], b["value"]))
            value = round((a["value"] + b["value"]) / 2, 3) if accepted else None
            note = ("iki beyin eyni rəqəmi eyni dövr üçün tapdı" if accepted else
                    f"{broken} beyin texniki xəta verdi: 2 saatdan sonra yenidən" if broken and tries < 3 else
                    "rəqəmlər və ya dövrlər üst-üstə düşmür, ya biri tapmadı: istifadə olunmur")
            self.db.execute("INSERT OR REPLACE INTO market_reports VALUES(?,?,?,?,?,?,?,?,?)",
                            (topic, (a.get("period") if accepted else day) or day, value, TOPICS[topic]["unit"], now,
                             json.dumps(a, ensure_ascii=False), json.dumps(b, ensure_ascii=False), int(bool(accepted)),
                             note))
            found += int(bool(accepted))
        rep("reporter", "done", note=f"{found}/{len(due)} rəqəm təsdiqləndi")
        return found

    def recent(self, limit: int = 12) -> list[dict]:
        return [{**dict(r), "a": json.loads(r["a"] or "null"), "b": json.loads(r["b"] or "null")}
                for r in self.db.execute("SELECT * FROM market_reports ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()]


def agents_view(db: DB, now: float | None = None) -> list[dict]:
    """The data agents for the news page: each one's last confirmed figure (period, value, both sources) and its last
    attempt (found / not agreed / not found), and when it asks next."""
    ensure(db)
    now = time.time() if now is None else now
    out = []
    for topic, t in TOPICS.items():
        acc = db.execute("SELECT * FROM market_reports WHERE topic=? AND accepted=1 ORDER BY ts DESC LIMIT 1",
                         (topic,)).fetchone()
        last = db.execute("SELECT * FROM market_reports WHERE topic=? ORDER BY ts DESC LIMIT 1", (topic,)).fetchone()
        src = []
        if acc:
            for side in ("a", "b"):
                try:
                    x = json.loads(acc[side] or "null") or {}
                except ValueError:
                    x = {}
                if x.get("url"):
                    src.append({"url": x["url"], "brain": x.get("brain")})
        d = datetime.fromtimestamp(now, timezone.utc)
        nxt = None
        for k in range(0, 8):
            day = datetime.fromtimestamp(now + k * 86400, timezone.utc)
            if day.weekday() in t["days"] and not (k == 0 and (d.hour >= t.get("hour", HOUR_UTC) and
                                                           db.get(f"reporter:{topic}:day") == day.strftime("%Y-%m-%d"))):
                nxt = day.replace(hour=t.get("hour", HOUR_UTC), minute=0, second=0).timestamp()
                if nxt < now and k == 0 and db.get(f"reporter:{topic}:day") != day.strftime("%Y-%m-%d"):
                    nxt = now
                break
        out.append({"id": topic, "name": t.get("name", topic), "group": t.get("group", ""), "unit": t["unit"],
                    "value": acc["value"] if acc else None, "period": acc["period"] if acc else None,
                    "found_ts": acc["ts"] if acc else None, "sources": src,
                    "last_ts": last["ts"] if last else None, "last_ok": bool(last and last["accepted"]),
                    "last_note": last["note"] if last else "hələ axtarmayıb", "next_ts": nxt})
    return out


def accepted(db: DB, topic: str) -> list[tuple[float, str, float]]:
    """(known_ts, period, value) of the confirmed figures, one per period (the first confirmation counts)."""
    ensure(db)
    out, seen = [], set()
    for r in db.execute("SELECT ts, period, value FROM market_reports WHERE topic=? AND accepted=1 ORDER BY ts",
                        (topic,)).fetchall():
        if r["period"] in seen:
            continue
        seen.add(r["period"])
        out.append((r["ts"], r["period"], r["value"]))
    return out
