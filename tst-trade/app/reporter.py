"""Bazar müxbiri (owner 2026-11-25: «an agent that keeps bringing the data we cannot download: India, from the news»).

The physical market's weekly and monthly figures that no free official feed gives us, found in published news by two
brains from two companies independently (the Rəqəm ovçusu way): each figure must come with a source link, and it is
used only when both brains found the same figure for the same period. Nothing is estimated; no price comes from a
brain — only a number printed in a news report (premium in dollars per ounce, tonnes, rupees).

Topics and when they are asked (most reports come out on Friday; monthly figures in the first half of the month):
- India premium/discount of local dealers over the official domestic price (Reuters «Asia gold», weekly)  Fri, Mon
- China premium over the global price (cross-check of the Shanghai Gold Exchange data)                     Fri, Mon
(India's gold ETF flow is no longer asked here: it comes from AMFI's official monthly report, feeds.amfi.)
- India's gold imports for the last month (tonnes)                                                        Wed
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
TOPICS = {
    "india_premium": {"days": (4, 0), "unit": "$/oz", "tol": 2.0,
                      "q": "Indian gold dealers' premium (positive) or discount (negative) over official domestic "
                           "prices (which include import and sales taxes), as reported in the most recent weekly "
                           "report (for example Reuters 'Asia Gold'). In US dollars per ounce. If a range is quoted, "
                           "give the mid-point (e.g. a discount of $10-$20 is -15)."},
    "china_premium": {"days": (4, 0), "unit": "$/oz", "tol": 3.0,
                      "q": "Chinese gold dealers' premium (positive) or discount (negative) over the global benchmark "
                           "spot price, as reported in the most recent weekly report (for example Reuters 'Asia Gold'). "
                           "In US dollars per ounce; mid-point if a range is quoted."},
    "india_imports": {"days": (2,), "unit": "tonnes", "tol": 0.10, "rel": True,
                      "q": "India's gold imports in the most recent month for which a figure has been published "
                           "(government data or a major news report), in metric tonnes."},
}
SYSTEM = ("You look up published figures about the physical gold market on the web. Report only a figure you actually "
          "find printed in a news report or official release, for the exact item asked, with the period it refers "
          "to. Never estimate or compute it yourself. If you cannot find it, set found to false. Answer ONLY with one "
          'JSON object: {"found": true|false, "value": number, "unit": "...", "period": "the week ending YYYY-MM-DD '
          'or the month YYYY-MM the figure refers to", "source_url": "the page you read it on"}')
HOUR_UTC = 13          # asked once on the scheduled days, after Asian and European reports are out


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
        if d.hour < HOUR_UTC:
            return []
        day = d.strftime("%Y-%m-%d")
        out = []
        for topic, t in TOPICS.items():
            if d.weekday() in t["days"] and self.db.get(f"reporter:{topic}:day") != day:
                out.append(topic)
        return out

    async def tick(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        due = self.due(now)
        if not due or not (self.keys.first("openai") or self.keys.first("anthropic")):
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
            a, b = (vals + [{}, {}])[:2]
            accepted = (a.get("value") is not None and b.get("value") is not None and a.get("period")
                        and a.get("period") == b.get("period") and _agree(topic, a["value"], b["value"]))
            value = round((a["value"] + b["value"]) / 2, 3) if accepted else None
            note = ("iki beyin eyni rəqəmi eyni dövr üçün tapdı" if accepted else
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
