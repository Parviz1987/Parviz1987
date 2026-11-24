"""The jobs of the brains that are connected.

Reader (Oxuyucu): new headlines -> for each: which metals, which way, how strong, what kind of event. Labels only.
Strategist (Strateq): once an hour, the forecast cards, macro, calendar and labelled news -> a short explanation in
Azerbaijani. A sentence with a number that is not in the facts is dropped (a brain never writes a price)."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time

from . import brains, brainviews, candles, forecast, judge, markets, signals
from .db import DB
from .keys import KeyStore

READER_EVERY, STRATEGIST_EVERY = 120, 3600
ALARM_GAP, ALARMS_PER_DAY = 15 * 60, 12          # an alarm analysis at most every 15 minutes, 12 a day (cost cap)
SCOUT_ALARMS_PER_DAY = 3                         # a fresh X search before the analysis, for news alarms only
READER_BATCH = 15

log = logging.getLogger("tst.brainjobs")

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
    "vermə; «sübut» statusu olmayan istiqaməti dəqiq kimi təqdim etmə və bunu açıq de.\n"
    "Ayrıca, hər metal üçün öz proqnozunu ver: p1h, p4h, p1d — qiymətin 1 saat, 4 saat və 1 gün sonra indikindən YUXARI "
    "olma ehtimalı (0..1). 0.5 «bilmirəm» deməkdir; yalnız faktlarda səbəb görəndə ondan uzaqlaş (adətən 0.4-0.6). "
    "Faktlar: hər metalın son hərəkətləri (moves, %), əlaqəli bazarlar (dollar, neft, səhm, VIX, istiqraz), son və "
    "gələn ABŞ rəqəmləri, xəbər etiketləri, makro. «why» sahəsində bir cümlə ilə əsas səbəbi yaz. Bu proqnozları Hakim "
    "sonra real qiymətlə yoxlayır: düz çıxmasa, etibar qazanmır.")
STRATEGIST_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "metals", "watch"],
    "properties": {
        "summary": {"type": "string"},
        "metals": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                              "required": ["symbol", "text", "p1h", "p4h", "p1d", "why"],
                                              "properties": {"symbol": {"type": "string"}, "text": {"type": "string"},
                                                             "p1h": {"type": "number"}, "p4h": {"type": "number"},
                                                             "p1d": {"type": "number"}, "why": {"type": "string"}}}},
        "watch": {"type": "array", "items": {"type": "string"}}}}

ANALYST2_SYSTEM = (
    "You are an independent precious-metals analyst. From the facts only (recent moves in %, linked markets, US "
    "releases, labelled news, macro, and 'what_just_happened' if something just happened), give for each of XAU, XAG, "
    "XPT, XPD the probability (0..1) that its price is HIGHER than now in 1 hour (p1h), 4 hours (p4h) and 1 day (p1d), "
    "and one sentence why. 0.5 means no edge; move away from it only for a reason in the facts (usually 0.4-0.6). "
    "Never invent numbers. Your answers are checked later against real prices.")
ANALYST2_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["metals"],
    "properties": {"metals": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["symbol", "p1h", "p4h", "p1d", "why"],
        "properties": {"symbol": {"type": "string"}, "p1h": {"type": "number"}, "p4h": {"type": "number"},
                       "p1d": {"type": "number"}, "why": {"type": "string"}}}}}}

NUM = re.compile(r"\d+(?:[.,]\d+)?")


SCOUT_EVERY, SCOUT_EVENT_EVERY = 4 * 3600, 30 * 60   # one search cost ~0.9 $ (counted high): the monthly cap lasts
SCOUT_SYSTEM = (
    "You are the Scout of a precious-metals forecasting desk. Use X search to find what moved or may "
    "move gold, silver, platinum and palladium in the LAST 3 HOURS: central banks and Fed speakers, US data surprises, "
    "geopolitics, tariffs and sanctions, ETF and central-bank buying, China and India demand, mine supply, big trader "
    "or analyst posts on X. Prefer primary sources and well-known accounts; skip rumours you cannot source. Do not "
    "state prices or price levels. Answer ONLY with one JSON object: {\"mood\": \"one short sentence in "
    "Azerbaijani about the overall picture\", \"items\": [{\"title\": \"short English headline\", \"url\": "
    "\"source link\", \"source\": \"account or site\", \"metals\": [\"XAU\"|\"XAG\"|\"XPT\"|\"XPD\"], "
    "\"direction\": \"up\"|\"down\"|\"neutral\", \"strength\": 0-3, \"why\": \"one sentence in "
    "Azerbaijani\"}]} with at most 8 items, most important first.")
SCOUT_USER = "Find the most market-moving metals news and posts of the last 3 hours now."


def strip_numbers(text: str) -> str:
    """Drop every sentence that holds a digit: a language model must not be the source of a price or a figure."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(p for p in parts if not re.search(r"\d", p)).strip()


def guard_numbers(text: str, facts: str) -> str:
    """Drop every sentence holding a number that does not appear in the facts."""
    known = {n.replace(",", ".") for n in NUM.findall(facts)}
    keep = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        nums = [n.replace(",", ".") for n in NUM.findall(sentence)]
        if all(n in known or n.rstrip("0").rstrip(".") in {k.rstrip("0").rstrip(".") for k in known} for n in nums):
            keep.append(sentence)
    return " ".join(keep).strip()


def _has(db: DB, table: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _moves(db: DB, sym: str, now: float) -> dict | None:
    """How far a market moved over the last 1 h, 4 h, 1 day and 1 week, in %, from finished candles only."""
    out = {}
    for name, tf, back in (("1h", "15m", 4), ("4h", "15m", 16), ("1d", "1h", 24), ("1w", "1d", 5)):
        rows = candles.closed(db, sym, tf, now, limit=back + 1)
        if len(rows) == back + 1 and rows[0]["c"]:
            out[name] = round((rows[-1]["c"] / rows[0]["c"] - 1) * 100, 3)
    return out or None


class BrainJobs:
    def __init__(self, db: DB, keys: KeyStore, feeds):
        self.db = db
        self.keys = keys
        self.feeds = feeds
        db.conn.executescript(SCHEMA)
        self.next_reader = 0.0
        self.next_strategist = 0.0
        from .hunter import Hunter
        self.hunter = Hunter(db, keys)
        self.activity = None      # app.activity.Hub, set by the app
        from .brainviews import SCHEMA as BV
        db.conn.executescript(BV)
        # A restart (every update) must not buy an extra search: the next one follows the last one's time.
        last = json.loads(db.get("scout:last") or "{}")
        self.next_scout = float(last.get("ts", 0)) + SCOUT_EVERY

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

    def facts(self, now: float, trigger: list[dict] | None = None) -> str:
        cards = []
        for sym in ("XAU", "XAG", "XPT", "XPD"):
            for h in forecast.HORIZONS:
                row = self.db.execute("SELECT method, p_up, lo80, hi80, price0 FROM forecasts WHERE symbol=? AND "
                                      "horizon=? AND mode='live' AND method='rw' ORDER BY issued_t DESC LIMIT 1",
                                      (sym, h)).fetchone()
                st = judge.stats(self.db, sym, h, "live", ttl=60)
                hist = judge.stats(self.db, sym, h, "history", ttl=300)
                verdict = judge.official(st if max(r["n"] for r in st) >= judge.MIN_N[h] else hist)
                cards.append({"metal": sym, "horizon": forecast.HORIZON_NAMES[h], "status": verdict["status"],
                              "price": round(row["price0"], 2) if row else None,
                              "range80": [round(row["lo80"], 2), round(row["hi80"], 2)] if row else None})
        news = [dict(r) for r in self.db.execute(
            "SELECT n.title, a.metals, a.direction, a.strength FROM news n JOIN news_ai a ON a.uid=n.uid "
            "WHERE n.ts > ? AND a.strength >= 2 ORDER BY n.ts DESC LIMIT 10", (now - 24 * 3600,)).fetchall()]
        moves = {}
        for sym in ("XAU", "XAG", "XPT", "XPD") + tuple(markets.saved(self.db).get("epics", {})):
            m = _moves(self.db, sym, now)
            if m:
                moves[sym] = m
        released = [dict(r) for r in self.db.execute(
            "SELECT event, estimate, actual, ts FROM releases WHERE actual IS NOT NULL AND ts BETWEEN ? AND ? "
            "ORDER BY ts DESC LIMIT 6", (now - 12 * 3600, now)).fetchall()] if _has(self.db, "releases") else []
        return json.dumps({"now_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(now)),
                           "what_just_happened": [s["text"] for s in (trigger or [])], "moves_pct": moves,
                           "released_last_12h": released,
                           "cards": cards, "macro": self.feeds.macro_view(),
                           "calendar": [{k: e[k] for k in ("title", "impact", "forecast", "previous", "actual")}
                                        for e in self.feeds.upcoming(now)[:8]],
                           "news": news}, ensure_ascii=False)

    def _rep(self, task: str, status: str, *a, **k) -> None:
        if self.activity is not None:
            self.activity.report(task, status, *a, **k)

    async def strategist(self, now: float, trigger: list[dict] | None = None) -> bool:
        """The hourly analysis, or at once after an alarm (trigger: the signals that woke it)."""
        self._rep("strateq", "working", "W1 Faktlar", 0.1, ("Həyəcan: " + trigger[0]["text"]) if trigger else "")
        facts = self.facts(now, trigger)
        self._rep("strateq", "working", "W2 Beyin", 0.35)
        data, how = await brains.run(self.db, self.keys, "strategist", STRATEGIST_SYSTEM,
                                     "Faktlar (JSON):\n" + facts, STRATEGIST_SCHEMA, max_tokens=3000)
        self._rep("strateq", "working", "W3 Rəqəm yoxlaması", 0.75)
        if data is None:
            self._state("strategist", "alınmadı: " + how)
            return False
        out = {"ts": now, "brain": how, "summary": guard_numbers(str(data.get("summary", "")), facts),
               "metals": [{"symbol": m.get("symbol"), "text": guard_numbers(str(m.get("text", "")), facts)}
                          for m in data.get("metals", []) if m.get("symbol") in ("XAU", "XAG", "XPT", "XPD")],
               "watch": [guard_numbers(str(w), facts) for w in data.get("watch", [])][:6]}
        self._rep("strateq", "working", "W4 Yaddaş", 0.9)
        self.db.put("strategist:last", json.dumps(out, ensure_ascii=False))
        rows = self._prob_rows(now, "strateq", data, how, trigger)
        brainviews.ensure(self.db)
        self.db.executemany("INSERT INTO brain_views(ts, source, metal, lean, note, horizon, p) VALUES(?,?,?,?,?,?,?)",
                            rows)
        await self.second_brain(now, facts, trigger)
        self._state("strategist", f"izah yazıldı · {how}")
        return True

    def _prob_rows(self, now: float, source: str, data: dict, how: str, trigger) -> list[tuple]:
        rows = []
        for m in data.get("metals", []):
            if m.get("symbol") not in ("XAU", "XAG", "XPT", "XPD"):
                continue
            for h, key in (("1h", "p1h"), ("4h", "p4h"), ("1d", "p1d")):
                try:
                    p = float(m.get(key))
                except (TypeError, ValueError):
                    continue
                if 0.0 <= p <= 1.0:
                    lean = 1 if p > 0.52 else -1 if p < 0.48 else 0
                    tag = "həyəcan · " if trigger else ""
                    rows.append((now, source, m["symbol"], lean, f"{tag}{how} · {str(m.get('why', ''))[:200]}", h, p))
        return rows

    async def second_brain(self, now: float, facts: str, trigger) -> bool:
        """The same facts to a brain of another company, which never sees the Strategist's answer."""
        if not self.keys.first(brains.config(self.db, "analyst2")["provider"]):
            return False
        data, how = await brains.run(self.db, self.keys, "analyst2", ANALYST2_SYSTEM, "Facts (JSON):\n" + facts,
                                     ANALYST2_SCHEMA, max_tokens=1500)
        if data is None:
            self._state("analyst2", "alınmadı: " + how)
            return False
        rows = self._prob_rows(now, "brain2", data, how, trigger)
        self.db.executemany("INSERT INTO brain_views(ts, source, metal, lean, note, horizon, p) VALUES(?,?,?,?,?,?,?)",
                            rows)
        self._state("analyst2", f"{len(rows)} ehtimal yazıldı · {how}")
        return True

    def last_explanation(self) -> dict | None:
        raw = self.db.get("strategist:last")
        return json.loads(raw) if raw else None

    # ---------- Scout: live X and web search (Grok) ----------
    async def scout(self, now: float) -> int:
        data, how = await brains.run(self.db, self.keys, "scout", SCOUT_SYSTEM, SCOUT_USER, {}, max_tokens=3000,
                                     search=True)
        if data is None:
            self._state("scout", "alınmadı: " + how)
            return 0
        items = []
        raw_items = data.get("items") if isinstance(data, dict) else None
        for it in (raw_items if isinstance(raw_items, list) else [])[:12]:
            if not isinstance(it, dict) or not str(it.get("title", "")).strip():
                continue
            try:
                strength = int(it.get("strength") or 0)
            except (TypeError, ValueError):
                strength = 0       # a model wrote "high" instead of a number: no strength rather than a crash
            url = str(it.get("url", ""))
            metals = [m for m in (it.get("metals") or []) if m in ("XAU", "XAG", "XPT", "XPD")] \
                if isinstance(it.get("metals"), list) else []
            items.append({"title": str(it["title"])[:240], "url": url if url.startswith(("https://", "http://")) else "",
                          "source": str(it.get("source", ""))[:60], "metals": metals,
                          "direction": it.get("direction") if it.get("direction") in ("up", "down", "neutral") else "neutral",
                          "strength": max(0, min(3, strength)),
                          # No prices from a language model: a sentence with a number is dropped.
                          "why": strip_numbers(str(it.get("why", ""))[:300])})
        rows = [{"uid": "grok:" + hashlib.sha1(i["title"].lower().encode()).hexdigest()[:16], "source": "Grok: X / veb",
                 "url": i["url"], "title": i["title"], "ts": now, "metals": ",".join(i["metals"])} for i in items]
        if rows:
            self.db.executemany("INSERT OR IGNORE INTO news(uid, source, url, title, ts, metals) "
                                "VALUES(:uid, :source, :url, :title, :ts, :metals)", rows)
        mood = data.get("mood", "") if isinstance(data, dict) else ""
        self.db.put("scout:last", json.dumps({"ts": now, "brain": how, "items": items,
                                              "mood": strip_numbers(str(mood)[:400])}))
        self._state("scout", f"{len(items)} xəbər tapıldı · {how}")
        return len(items)

    def last_scout(self) -> dict | None:
        raw = self.db.get("scout:last")
        return json.loads(raw) if raw else None

    async def tick(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self.hunter.activity = self.activity
        try:
            n = await self.hunter.tick(now)
            if n:
                self._state("hunter", f"{n} rəqəm tapıldı və iki beyin təsdiqlədi")
        except Exception:
            log.exception("hunter failed")
        if now >= self.next_scout and self.feeds is not None:
            # Every 4 hours while the market is open; every 30 minutes around a high-impact US release.
            from .engine import market_open
            hot = self.feeds.event_mode(now) is not None
            self.next_scout = now + (SCOUT_EVENT_EVERY if hot else SCOUT_EVERY)
            if market_open(now) and self.keys.first("xai"):
                self._rep("scout", "working", note="X-də axtarır")
                n = await self.scout(now)
                self._rep("scout", "done" if n else "error", note=self.state("scout").get("message", ""))
        if now >= self.next_reader:
            self.next_reader = now + READER_EVERY
            self._rep("reader", "working", note="başlıqlar qiymətləndirilir")
            n = await self.reader(now)
            self._rep("reader", "done", note=f"{n} başlıq" if n else self.state("reader").get("message", "yeni başlıq yoxdur"))
        # the nerves: a strong headline, a confirmed US figure or a sharp move wakes the analysis at once
        try:
            syms = ["XAU", "XAG", "XPT", "XPD"] + list(markets.saved(self.db).get("epics", {}))
            signals.scan(self.db, now, syms)
            alarm = signals.pending(self.db, now)
        except Exception:
            log.exception("signals failed")
            alarm = []
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        count = json.loads(self.db.get("alarm:count") or "{}")
        if count.get("day") != day:
            count = {"day": day, "n": 0, "scout": 0}
        if alarm and now - float(self.db.get("alarm:last") or 0) >= ALARM_GAP and count["n"] < ALARMS_PER_DAY:
            self.db.put("alarm:last", str(now))
            count["n"] += 1
            if any(a["kind"] in ("news", "flow") for a in alarm) and count["scout"] < SCOUT_ALARMS_PER_DAY \
                    and self.keys.first("xai"):
                count["scout"] += 1
                self._rep("scout", "working", note="həyəcan: X-də dərhal axtarır")
                await self.scout(now)
                self._rep("scout", "done", note=self.state("scout").get("message", ""))
            self.db.put("alarm:count", json.dumps(count))
            signals.mark(self.db, [a["id"] for a in alarm], now)
            ok = await self.strategist(now, alarm)
            self.next_strategist = now + STRATEGIST_EVERY      # the hourly one restarts from here
            self._rep("strateq", "done" if ok else "error", note="həyəcan təhlili: " + alarm[0]["text"][:100])
        elif now >= self.next_strategist:
            self.next_strategist = now + STRATEGIST_EVERY
            ok = await self.strategist(now)
            self._rep("strateq", "done" if ok else "error", note=self.state("strategist").get("message", ""))


def reader_score(db: DB, now: float | None = None, horizon: int = 3600) -> dict:
    """The Judge for the Reader brain: when it labels a headline "up" or "down" for a metal, did that metal move that
    way over the next hour (from the labelling time, one-minute closes)? Neutral labels are not scored.
    Headlines about one event are not independent, so this is a first look, not proof."""
    import math
    now = time.time() if now is None else now
    rows = db.execute("SELECT a.ts, a.metals, a.direction, a.strength FROM news_ai a WHERE a.direction IN ('up', 'down') "
                      "AND a.ts < ? AND a.ts > ?", (now - horizon - 120, now - 30 * 86400)).fetchall()

    def px(sym: str, t: float) -> float | None:
        """Close of the last minute that had ENDED by time t (never a price from after t)."""
        r = db.execute("SELECT t, c FROM candles WHERE symbol=? AND tf='1m' AND t<=? ORDER BY t DESC LIMIT 1",
                       (sym, int(t) - 60)).fetchone()
        return r["c"] if r and t - r["t"] < 360 else None

    by: dict[int, list[int]] = {}
    ups = total = 0
    for r in rows:
        for sym in [m for m in (r["metals"] or "").split(",") if m in ("XAU", "XAG", "XPT", "XPD")]:
            a, b = px(sym, r["ts"]), px(sym, r["ts"] + horizon)
            if a is None or b is None or a == b:
                continue
            hit = int((b > a) == (r["direction"] == "up"))
            by.setdefault(int(r["strength"] or 0), []).append(hit)
            ups += int(b > a)
            total += 1
    out = []
    for strength in sorted(by):
        hs = by[strength]
        n, k = len(hs), sum(hs)
        z = (k - 0.5 - n * 0.5) / math.sqrt(n * 0.25) if n else 0
        out.append({"strength": strength, "n": n, "hit_rate": k / n if n else None,
                    "p": 1 - 0.5 * (1 + math.erf(z / math.sqrt(2))) if n else None})
    alln = sum(len(v) for v in by.values())
    allk = sum(sum(v) for v in by.values())
    return {"horizon_s": horizon, "rows": out, "n": alln, "hit_rate": allk / alln if alln else None,
            "up_rate": ups / total if total else None}
