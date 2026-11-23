"""Rəqəm ovçusu (figure hunter): the actual value of a US release, found on the web by two brains independently.

Why: the surprise method needs the released figure next to the estimate. Forex Factory gives the time and the
estimate but not the actual; the owner's FMP plan has no calendar. Two brains from two companies search the web; a
figure is used only when both found it and they agree (and each gave a source link). Otherwise nothing is used.

When: a High or Medium US release that came out 2 to 40 minutes ago and has no actual yet; asked at most three
times (about 2, 8 and 20 minutes after the release), so a figure published late is still caught."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

from . import brains, surprise
from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS hunter_log (uid TEXT NOT NULL, ts REAL NOT NULL, event TEXT, a TEXT, b TEXT,
  accepted INTEGER NOT NULL, note TEXT);
CREATE INDEX IF NOT EXISTS hunter_log_uid ON hunter_log(uid);
"""
ASK_AFTER = (120, 480, 1200)          # seconds after the release
GIVE_UP = 2400

SYSTEM = ("You look up officially released US economic figures on the web. Report only a figure you actually find "
          "published (official agency site or a major financial news site) for the exact release asked. If it is not "
          "published yet or you are unsure, set found to false. Never estimate. Answer ONLY with one JSON object: "
          '{"found": true|false, "actual": "the figure exactly as published, with its unit, e.g. 0.3% or 227K", '
          '"source_url": "the page you read it on", "released_utc": "release time if shown"}')


def _same(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(1e-9, abs(a) * 1e-6)


class Hunter:
    def __init__(self, db: DB, keys):
        self.db = db
        self.keys = keys
        db.conn.executescript(SCHEMA)
        surprise.ensure(db)

    def due(self, now: float) -> list[dict]:
        rows = self.db.execute(
            "SELECT title, ts, impact, forecast FROM events WHERE country='USD' AND impact IN ('High', 'Medium') "
            "AND ts BETWEEN ? AND ? AND forecast IS NOT NULL", (now - GIVE_UP, now - ASK_AFTER[0])).fetchall()
        out = []
        for r in rows:
            uid = "ff:" + hashlib.sha1(f"{r['title']}|{r['ts']}".encode()).hexdigest()[:16]
            if self.db.execute("SELECT 1 FROM releases WHERE uid=? AND actual IS NOT NULL", (uid,)).fetchone():
                continue
            tries = self.db.execute("SELECT COUNT(*) FROM hunter_log WHERE uid=?", (uid,)).fetchone()[0]
            if tries >= len(ASK_AFTER) or now - r["ts"] < ASK_AFTER[tries]:
                continue
            out.append({**dict(r), "uid": uid})
        return out

    async def tick(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        if not (self.keys.first("openai") or self.keys.first("anthropic")):
            return 0
        found = 0
        for ev in self.due(now)[:3]:
            when = datetime.fromtimestamp(ev["ts"], timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            user = (f"US release: \"{ev['title']}\" scheduled {when}. Consensus forecast was {ev['forecast']}. "
                    "What is the actual figure that was released?")
            answers = await brains.run_both(self.db, self.keys, "hunter", SYSTEM, user, max_tokens=1500)
            vals = []
            for data, how in answers:
                ok = isinstance(data, dict) and data.get("found") is True and \
                    str(data.get("source_url", "")).startswith(("https://", "http://"))
                vals.append({"value": surprise._num(data.get("actual")) if ok else None,
                             "raw": str(data.get("actual"))[:40] if ok else None,
                             "url": str(data.get("source_url"))[:300] if ok else None, "brain": how})
            accepted = len(vals) == 2 and _same(vals[0]["value"], vals[1]["value"])
            note = "iki beyin eyni rəqəmi tapdı" if accepted else \
                "rəqəmlər üst-üstə düşmür və ya biri tapmadı: istifadə olunmur"
            self.db.execute("INSERT INTO hunter_log VALUES(?,?,?,?,?,?,?)",
                            (ev["uid"], now, ev["title"], json.dumps(vals[0] if vals else None, ensure_ascii=False),
                             json.dumps(vals[1] if len(vals) > 1 else None, ensure_ascii=False), int(accepted), note))
            if accepted:
                surprise.store(self.db, [{
                    "uid": ev["uid"], "ts": ev["ts"], "event": ev["title"], "impact": ev["impact"],
                    "estimate": surprise._num(ev["forecast"]), "previous": None, "actual": vals[0]["value"],
                    "raw_date": datetime.fromtimestamp(ev["ts"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "known_ts": now}])
                found += 1
        return found

    def recent(self, limit: int = 10) -> list[dict]:
        return [{**dict(r), "a": json.loads(r["a"] or "null"), "b": json.loads(r["b"] or "null")}
                for r in self.db.execute("SELECT * FROM hunter_log ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()]
