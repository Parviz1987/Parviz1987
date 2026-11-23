"""The jobs of the brains that are connected.

Reader (Oxuyucu): new headlines -> for each: which metals, which way, how strong, what kind of event. Labels only.
Strategist (Strateq): once an hour, the forecast cards, macro, calendar and labelled news -> a short explanation in
Azerbaijani. A sentence with a number that is not in the facts is dropped (a brain never writes a price)."""
from __future__ import annotations

import json
import re
import time

from . import brains, forecast, judge
from .db import DB
from .keys import KeyStore

READER_EVERY, STRATEGIST_EVERY = 120, 3600
READER_BATCH = 15

SCHEMA = """
CREATE TABLE IF NOT EXISTS news_ai (uid TEXT PRIMARY KEY, ts REAL, event TEXT, metals TEXT, direction TEXT,
  strength INTEGER, brain TEXT);
"""

READER_SYSTEM = (
    "You label financial headlines for a precious-metals desk. For each headline say which of XAU, XAG, XPT, XPD it "
    "is likely to move, the likely direction for those metals (up, down or neutral), the strength 0-3 (0 = no effect, "
    "3 = major market mover) and a short event type (e.g. fed, inflation, jobs, geopolitics, dollar, supply, demand, "
    "other). Judge only from the headline. Do not invent facts. If unclear, use neutral and strength 0.")
READER_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "metals", "direction", "strength", "event"],
        "properties": {
            "id": {"type": "string"},
            "metals": {"type": "array", "items": {"type": "string", "enum": ["XAU", "XAG", "XPT", "XPD"]}},
            "direction": {"type": "string", "enum": ["up", "down", "neutral"]},
            "strength": {"type": "integer", "enum": [0, 1, 2, 3]},
            "event": {"type": "string"}}}}}}

STRATEGIST_SYSTEM = (
    "Sən qiymətli metallar üzrə analitiksən. Sənə proqnoz kartları, Hakimin statusları, makro göstəricilər, "
    "iqtisadi təqvim və xəbər etiketləri verilir. Azərbaycan dilində, sadə və qısa izah yaz. Qaydalar: yalnız verilən "
    "faktlardan istifadə et; faktlarda olmayan heç bir rəqəm yazma; qiymət proqnozu uydurma; alış-satış məsləhəti "
    "vermə; «sübut» statusu olmayan istiqaməti dəqiq kimi təqdim etmə və bunu açıq de.")
STRATEGIST_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "metals", "watch"],
    "properties": {
        "summary": {"type": "string"},
        "metals": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                              "required": ["symbol", "text"],
                                              "properties": {"symbol": {"type": "string"}, "text": {"type": "string"}}}},
        "watch": {"type": "array", "items": {"type": "string"}}}}

NUM = re.compile(r"\d+(?:[.,]\d+)?")


def guard_numbers(text: str, facts: str) -> str:
    """Drop every sentence holding a number that does not appear in the facts."""
    known = {n.replace(",", ".") for n in NUM.findall(facts)}
    keep = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        nums = [n.replace(",", ".") for n in NUM.findall(sentence)]
        if all(n in known or n.rstrip("0").rstrip(".") in {k.rstrip("0").rstrip(".") for k in known} for n in nums):
            keep.append(sentence)
    return " ".join(keep).strip()


class BrainJobs:
    def __init__(self, db: DB, keys: KeyStore, feeds):
        self.db = db
        self.keys = keys
        self.feeds = feeds
        db.conn.executescript(SCHEMA)
        self.next_reader = 0.0
        self.next_strategist = 0.0

    def _state(self, slot: str, msg: str) -> None:
        self.db.put(f"brainjob:{slot}", json.dumps({"ts": time.time(), "message": msg[:300]}))

    def state(self, slot: str) -> dict:
        return json.loads(self.db.get(f"brainjob:{slot}") or "{}")

    async def reader(self, now: float) -> int:
        rows = self.db.execute(
            "SELECT n.uid, n.title FROM news n LEFT JOIN news_ai a ON a.uid = n.uid WHERE a.uid IS NULL AND n.ts > ? "
            "ORDER BY n.ts DESC LIMIT ?", (now - 6 * 3600, READER_BATCH)).fetchall()
        if not rows:
            return 0
        lines = "\n".join(f"{r['uid']}: {r['title']}" for r in rows)
        data, how = await brains.run(self.db, self.keys, "reader", READER_SYSTEM, "Headlines (id: text):\n" + lines,
                                     READER_SCHEMA, max_tokens=2500)
        if data is None:
            self._state("reader", "alınmadı: " + how)
            return 0
        ids = {r["uid"] for r in rows}
        saved = 0
        for it in data.get("items", []):
            if it.get("id") not in ids:
                continue   # a brain may only label the headlines it was given
            self.db.execute("INSERT OR REPLACE INTO news_ai VALUES(?,?,?,?,?,?,?)",
                            (it["id"], now, str(it.get("event", ""))[:40], ",".join(it.get("metals", [])),
                             it.get("direction", "neutral"), int(it.get("strength", 0)), how))
            saved += 1
        self._state("reader", f"{saved} başlıq qiymətləndirildi · {how}")
        return saved

    def facts(self, now: float) -> str:
        cards = []
        for sym in ("XAU", "XAG", "XPT", "XPD"):
            for h in forecast.HORIZONS:
                row = self.db.execute("SELECT method, p_up, lo80, hi80, price0 FROM forecasts WHERE symbol=? AND "
                                      "horizon=? AND mode='live' AND method='rw' ORDER BY issued_t DESC LIMIT 1",
                                      (sym, h)).fetchone()
                st = judge.stats(self.db, sym, h, "live")
                hist = judge.stats(self.db, sym, h, "history")
                verdict = judge.official(st if max(r["n"] for r in st) >= judge.MIN_N[h] else hist)
                cards.append({"metal": sym, "horizon": forecast.HORIZON_NAMES[h], "status": verdict["status"],
                              "price": round(row["price0"], 2) if row else None,
                              "range80": [round(row["lo80"], 2), round(row["hi80"], 2)] if row else None})
        news = [dict(r) for r in self.db.execute(
            "SELECT n.title, a.metals, a.direction, a.strength FROM news n JOIN news_ai a ON a.uid=n.uid "
            "WHERE n.ts > ? AND a.strength >= 2 ORDER BY n.ts DESC LIMIT 10", (now - 24 * 3600,)).fetchall()]
        return json.dumps({"cards": cards, "macro": self.feeds.macro_view(),
                           "calendar": [{k: e[k] for k in ("title", "impact", "forecast", "previous", "actual")}
                                        for e in self.feeds.upcoming(now)[:8]],
                           "news": news}, ensure_ascii=False)

    async def strategist(self, now: float) -> bool:
        facts = self.facts(now)
        data, how = await brains.run(self.db, self.keys, "strategist", STRATEGIST_SYSTEM,
                                     "Faktlar (JSON):\n" + facts, STRATEGIST_SCHEMA, max_tokens=3000)
        if data is None:
            self._state("strategist", "alınmadı: " + how)
            return False
        out = {"ts": now, "brain": how, "summary": guard_numbers(str(data.get("summary", "")), facts),
               "metals": [{"symbol": m.get("symbol"), "text": guard_numbers(str(m.get("text", "")), facts)}
                          for m in data.get("metals", []) if m.get("symbol") in ("XAU", "XAG", "XPT", "XPD")],
               "watch": [guard_numbers(str(w), facts) for w in data.get("watch", [])][:6]}
        self.db.put("strategist:last", json.dumps(out, ensure_ascii=False))
        self._state("strategist", f"izah yazıldı · {how}")
        return True

    def last_explanation(self) -> dict | None:
        raw = self.db.get("strategist:last")
        return json.loads(raw) if raw else None

    async def tick(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        if now >= self.next_reader:
            self.next_reader = now + READER_EVERY
            await self.reader(now)
        if now >= self.next_strategist:
            self.next_strategist = now + STRATEGIST_EVERY
            await self.strategist(now)
