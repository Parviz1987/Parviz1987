"""The jobs of the brains that are connected.

Reader (Oxuyucu): new headlines -> for each: which metals, which way, how strong, what kind of event. Labels only.
Strategist (Strateq): once an hour, the forecast cards, macro, calendar and labelled news -> a short explanation in
Azerbaijani. A sentence with a number that is not in the facts is dropped (a brain never writes a price)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time

from . import brains, brainviews, candles, cards, forecast, heartbeat, judge, markets, newsevents, signals
from .db import DB
from .keys import KeyStore

READER_EVERY, STRATEGIST_EVERY = 120, 3600
SECOND_EVERY = 4 * 3600          # the second analyst and the debate (plan 3.3, 27.11)
ALARM_GAP, ALARMS_PER_DAY = 15 * 60, 12          # an alarm analysis at most every 15 minutes, 12 a day (cost cap)
SCOUT_ALARMS_PER_DAY = 3
SLEEP_HOUR_UTC = 6                               # 01:00 New York: the nightly review (calibration and lessons)                         # a fresh X search before the analysis, for news alarms only
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
    "sonra real qiymətlə yoxlayır: düz çıxmasa, etibar qazanmır. Hər metal üçün həmçinin: «counter» — əks ssenari, yəni "
    "qiyməti əks tərəfə apara biləcək hadisə (bir cümlə); «invalidation» — hansı müşahidə sənin fikrini zəiflədər (bir "
    "cümlə, faktlardakı göstəricilərlə); «next_update» — bu fikir nə vaxt yenilənməlidir: vaxt və ya konkret hadisə "
    "(təqvimdən). Bunlar proqnoz kartında dondurulur və sonra nəticə ilə müqayisə olunur. Faktlarla birlikdə «BİLİK "
    "KİTABI» verilir: onun fundamental və bazarlar arası qaydaları ilə işlə, fikrinin əsaslandığı qaydaların id-lərini "
    "«rules» sahəsinə yaz; Hakimin «zəif» və ya «yox» dediyi qaydaya az çəki ver. «history_analogs» varsa: bu, hadisələr "
    "kitabxanasıdır — keçmişdə eyni hadisə eyni nəticə ilə (gözləntidən yuxarı / yaxın / aşağı) çıxanda metalın necə "
    "hərəkət etdiyi (n hal, up_share qalxma payı, mean_pct orta %); yalnız kölgə sınağından keçən metal və horizontlar "
    "verilir. Onu bir səbəb kimi işlət, rəqəmlərini olduğu kimi götür.")
STRATEGIST_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "metals", "watch"],
    "properties": {
        "summary": {"type": "string"},
        "metals": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                              "required": ["symbol", "text", "p1h", "p4h", "p1d", "why", "counter",
                                                           "invalidation", "next_update", "rules"],
                                              "properties": {"symbol": {"type": "string"}, "text": {"type": "string"},
                                                             "p1h": {"type": "number"}, "p4h": {"type": "number"},
                                                             "p1d": {"type": "number"}, "why": {"type": "string"},
                                                             "counter": {"type": "string"},
                                                             "invalidation": {"type": "string"},
                                                             "next_update": {"type": "string"},
                                                             "rules": {"type": "array", "items": {"type": "string"}}}}},
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

# Müzakirə (debate, the TradingAgents idea): one brain argues the strongest honest case for UP, another for DOWN, from
# the same facts; a third brain weighs both and gives the probabilities. Judged like every other analyst.
BULL_SYSTEM = (
    "You are the BULL analyst of a precious-metals desk. From the facts only, make the strongest honest case that each "
    "of XAU, XAG, XPT, XPD will be HIGHER in the next hours to a day: 2-3 concrete reasons per metal, citing the facts. "
    "If the facts give no good reason, say so plainly. Never invent numbers.")
BEAR_SYSTEM = BULL_SYSTEM.replace("BULL", "BEAR").replace("HIGHER", "LOWER")
CASE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["metals"],
    "properties": {"metals": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["symbol", "case"],
        "properties": {"symbol": {"type": "string"}, "case": {"type": "string"}}}}}}
DEBATE_JUDGE_SYSTEM = (
    "You judge a debate on precious metals. You get the facts, the BULL case and the BEAR case. For each of XAU, XAG, "
    "XPT, XPD weigh which arguments the facts support better (an argument not backed by the facts counts for nothing) "
    "and give the probability (0..1) that the price is HIGHER than now in 1 hour (p1h), 4 hours (p4h) and 1 day (p1d), "
    "and one sentence why. 0.5 = the cases balance. Your answers are checked later against real prices.")

CHARTIST_SYSTEM = (
    "You are a professional technical analyst of precious metals. You get, for each of XAU, XAG, XPT, XPD, recent "
    "candles on three timeframes (1 hour, 4 hours, 1 day: time, open, high, low, close, tick volume v when counted) "
    "and computed indicators (EMA 20/50/200, RSI 14, MACD, Stochastic 14/3, Bollinger 20/2, ATR 14, ADX 14 with +DI/-DI "
    "(trend strength: < 20 no trend, so trust reversal rules; > 25 strong trend, so trust trend rules), yesterday's pivot "
    "points P/R1/S1, the last swing highs and lows, Fibonacci levels of the recent swing). Read the charts like a "
    "complete trader, through every school: classic (trend lines, support and resistance, pivots), chart patterns "
    "(double top/bottom, head and shoulders, triangle, wedge, flag), candles, trend indicators, oscillators, volatility, "
    "volume (when counted), Fibonacci retracements and extensions, Dow structure, Elliott (wave 3 start, 5 waves done), "
    "Wyckoff (spring, upthrust), price action (liquidity sweep, break of structure, order block) and intermarket (the "
    "metal ratio). Say which agree and which disagree. Then give the probability (0..1) that the price is HIGHER than the last close in 1 hour "
    "(p1h), 4 hours (p4h) and 1 day (p1d). 0.5 = no edge; move away from it only when the chart gives a reason (usually "
    "0.4-0.6). Write 'trend', 'levels' and 'why' in Azerbaijani, short. Use ONLY prices that appear in the data; never "
    "invent levels. No news, no macro: charts only. Your answers are checked later against real prices. "
    "Work by the house rulebook (BİLİK KİTABI) given with the data: apply its rules, list the ids of the rules your "
    "view rests on in 'rules', give weight according to each rule's measured record (a rule marked 'zəif' or 'yox' "
    "deserves little weight), and fill 'counter' (what would turn the market the other way) and 'invalidation' "
    "(which price or observation cancels your view). 'rules_firing_now' lists what our own code detected.")
CHARTIST_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["metals"],
    "properties": {"metals": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["symbol", "trend", "levels", "pattern", "p1h", "p4h", "p1d", "why", "rules", "counter",
                     "invalidation"],
        "properties": {"symbol": {"type": "string"}, "trend": {"type": "string"}, "levels": {"type": "string"},
                       "pattern": {"type": "string"}, "p1h": {"type": "number"}, "p4h": {"type": "number"},
                       "p1d": {"type": "number"}, "why": {"type": "string"},
                       "rules": {"type": "array", "items": {"type": "string"}},
                       "counter": {"type": "string"}, "invalidation": {"type": "string"}}}}}}
CHART_BARS = {"1h": 48, "4h": 30, "1d": 40}

NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _ema(xs: list[float], n: int) -> float | None:
    if len(xs) < n:
        return None
    k, e = 2 / (n + 1), sum(xs[:n]) / n
    for x in xs[n:]:
        e = e + k * (x - e)
    return e


def _rsi(xs: list[float], n: int = 14) -> float | None:
    if len(xs) <= n:
        return None
    gains = [max(0.0, b - a) for a, b in zip(xs, xs[1:])]
    losses = [max(0.0, a - b) for a, b in zip(xs, xs[1:])]
    g, l = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(gains)):
        g, l = (g * (n - 1) + gains[i]) / n, (l * (n - 1) + losses[i]) / n
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


def chart_facts(db: DB, now: float) -> str:
    """The charts as text for the Chartist: candles on three timeframes and the indicators computed by code."""
    out = {}
    for sym in ("XAU", "XAG", "XPT", "XPD"):
        d = {}
        for tf, n in CHART_BARS.items():
            rows = candles.closed(db, sym, tf, now, limit=260)
            if len(rows) < 30:
                continue
            closes = [r["c"] for r in rows]
            dec = 2 if closes[-1] >= 100 else 3
            r_ = lambda v: None if v is None else round(v, dec)
            e12, e26 = _ema(closes, 12), _ema(closes, 26)
            seg = rows[-100:]
            hi, lo = max(r["h"] for r in seg), min(r["l"] for r in seg)
            from . import patterns, rules as rules_
            ind = rules_.Ind(rows)
            hs, ls = rules_._swings(rows, len(rows) - 100, len(rows))
            zz = patterns.zigzag(rows, hs, ls)[-6:]
            prev_day = [r for r in rows if patterns._period_key(r["t"], tf) ==
                        max((patterns._period_key(x["t"], tf) for x in rows
                             if patterns._period_key(x["t"], tf) < patterns._period_key(rows[-1]["t"], tf)), default=-1)]
            piv = None
            if prev_day:
                ph, pl, pc = max(r["h"] for r in prev_day), min(r["l"] for r in prev_day), prev_day[-1]["c"]
                pp = (ph + pl + pc) / 3
                piv = {"P": r_(pp), "R1": r_(2 * pp - pl), "S1": r_(2 * pp - ph)}
            d[tf] = {"candles": [[time.strftime("%m-%d %H:%M", time.gmtime(r["t"])), r_(r["o"]), r_(r["h"]), r_(r["l"]),
                                  r_(r["c"])] + ([r["v"]] if r.get("v") else []) for r in rows[-n:]],
                     "stoch_k": None if ind.sk[-1] is None else round(ind.sk[-1], 1),
                     "stoch_d": None if ind.sd[-1] is None else round(ind.sd[-1], 1),
                     "boll_up": r_(ind.bbu[-1]), "boll_low": r_(ind.bbl[-1]), "atr14": r_(ind.atr[-1]),
                     "adx14": None if ind.adx[-1] is None else round(ind.adx[-1], 1),
                     "di_plus": None if ind.pdi[-1] is None else round(ind.pdi[-1], 1),
                     "di_minus": None if ind.mdi[-1] is None else round(ind.mdi[-1], 1),
                     "pivot": piv,
                     "swings": [[time.strftime("%m-%d %H:%M", time.gmtime(rows[j]["t"])), k, r_(p)] for j, k, p in zz],
                     "ema20": r_(_ema(closes, 20)), "ema50": r_(_ema(closes, 50)), "ema200": r_(_ema(closes, 200)),
                     "rsi14": None if _rsi(closes) is None else round(_rsi(closes), 1),
                     "macd": None if e12 is None or e26 is None else r_(e12 - e26),
                     "high_100": r_(hi), "low_100": r_(lo),
                     "fib_382": r_(hi - 0.382 * (hi - lo)), "fib_500": r_(hi - 0.5 * (hi - lo)),
                     "fib_618": r_(hi - 0.618 * (hi - lo))}
        if d:
            out[sym] = d
    from . import learning, playbook, rules
    rec = rules.short_records(rules.records(db))
    firing = {sym: [f"{x['tf']} {x['rule']} {'yuxarı' if x['dir'] > 0 else 'aşağı'}: {x['note']}"
                    for x in rules.active_now(db, sym)] for sym in out}
    return json.dumps({"now_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(now)), "charts": out,
                       "rules_firing_now": firing,
                       "rulebook": playbook.text_for(playbook.CHART_AREAS, rec,
                                                     learning.accepted_rules(db))},
                      ensure_ascii=False)


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
        db.script(SCHEMA)
        self.next_reader = 0.0
        self.next_strategist = 0.0
        from .hunter import Hunter
        self.hunter = Hunter(db, keys)
        from .reporter import Reporter
        self.reporter = Reporter(db, keys)
        self.activity = None      # app.activity.Hub, set by the app
        from .brainviews import SCHEMA as BV
        db.script(BV)
        # A restart (every update) must not buy an extra search: the next one follows the last one's time.
        last = json.loads(db.get("scout:last") or "{}")
        self.next_scout = float(last.get("ts", 0)) + SCOUT_EVENT_EVERY   # 27.11: routine searches only in the window
        # Nor an extra strategist round (strategist, second analyst, debate, chart reader: all paid): on 2026-11-27 a
        # night of deploys ran it again after every restart. The hourly one follows the last round's time.
        ran = json.loads(db.get("brainjob:strategist") or "{}").get("ts")
        if ran:
            self.next_strategist = float(ran) + STRATEGIST_EVERY

    def _state(self, slot: str, msg: str) -> None:
        self.db.put(f"brainjob:{slot}", json.dumps({"ts": time.time(), "message": msg[:300]}))

    def state(self, slot: str) -> dict:
        return json.loads(self.db.get(f"brainjob:{slot}") or "{}")

    async def reader(self, now: float) -> int:
        # Block 17: one story copied by many sites is one event; only its first headline is read (and paid for)
        ev = await asyncio.to_thread(newsevents.assign, self.db, now)
        if ev["headlines"]:
            c = newsevents.day_counts(self.db, now)
            self._rep("events", "done", note=f"{ev['headlines']} yeni başlıq → {ev['new_events']} yeni hadisə · "
                                             f"24 saat: {c['headlines']} başlıq = {c['events']} hadisə")
        rows = self.db.execute(
            "SELECT n.uid, n.title FROM news n LEFT JOIN news_ai a ON a.uid = n.uid "
            "LEFT JOIN news_event e ON e.uid = n.uid "
            "WHERE a.uid IS NULL AND n.ts > ? AND (e.uid IS NULL OR e.uid = (SELECT e2.uid FROM news_event e2 "
            "WHERE e2.event_id = e.event_id ORDER BY e2.ts, e2.uid LIMIT 1)) "
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
                            (it["id"], time.time(), str(it.get("event", ""))[:40], ",".join(it.get("metals", [])),
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
                verdict = judge.verdict(self.db, sym, h)           # the one verdict the owner sees too
                cards.append({"metal": sym, "horizon": forecast.HORIZON_NAMES[h], "status": verdict["status"],
                              "price": round(row["price0"], 2) if row else None,
                              "range80": [round(row["lo80"], 2), round(row["hi80"], 2)] if row else None})
        news = [dict(r) for r in self.db.execute(
            "SELECT n.title, a.metals, a.direction, a.strength FROM news n JOIN news_ai a ON a.uid=n.uid "
            "WHERE n.ts > ? AND a.strength >= 2 ORDER BY n.ts DESC LIMIT 10", (now - 24 * 3600,)).fetchall()]
        moves = {}
        from .feeds import ETF_SYMBOLS
        for sym in ("XAU", "XAG", "XPT", "XPD") + tuple(markets.saved(self.db).get("epics", {})) + ETF_SYMBOLS:
            m = _moves(self.db, sym, now)
            if m:
                moves[sym] = m
        released = [dict(r) for r in self.db.execute(
            "SELECT event, estimate, actual, ts FROM releases WHERE actual IS NOT NULL AND ts BETWEEN ? AND ? "
            "ORDER BY ts DESC LIMIT 6", (now - 12 * 3600, now)).fetchall()] if _has(self.db, "releases") else []
        from . import eventlib, learning, playbook
        upcoming = self.feeds.upcoming(now)[:8] if self.feeds is not None else []
        try:     # the history library's analogs, only where its shadow test passed (app/eventlib.py)
            analogs = eventlib.for_brains(self.db, upcoming, released, now)
        except Exception as e:
            log.warning("eventlib analogs: %s", e)
            analogs = []
        return json.dumps({"now_utc": time.strftime("%Y-%m-%d %H:%M", time.gmtime(now)),
                           "rulebook": playbook.text_for(("Fundamental", "Bazarlar arası", "Öyrənilmiş"), None,
                                                         learning.accepted_rules(self.db)),
                           "what_just_happened": [s["text"] for s in (trigger or [])], "moves_pct": moves,
                           "released_last_12h": released,
                           "fed_odds_kalshi": self.feeds.fed_odds() if self.feeds is not None else [],
                           "cards": cards, "macro": self.feeds.macro_view(),
                           "calendar": [{k: e[k] for k in ("title", "impact", "forecast", "previous", "actual")}
                                        for e in self.feeds.upcoming(now)[:8]],
                           "news": news, "history_analogs": analogs}, ensure_ascii=False)

    def _rep(self, task: str, status: str, *a, **k) -> None:
        if self.activity is not None:
            self.activity.report(task, status, *a, **k)

    async def strategist(self, now: float, trigger: list[dict] | None = None) -> bool:
        """The hourly analysis, or at once after an alarm (trigger: the signals that woke it)."""
        self._rep("strateq", "working", "W1 Faktlar", 0.1,
                  (self._chain(trigger) + ": " + trigger[0]["text"]) if trigger else "saatlıq")
        facts = await asyncio.to_thread(self.facts, now, trigger)    # the Judge's numbers: heavy, off the loop
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
        self.db.executemany("INSERT INTO brain_views(ts, source, metal, lean, note, horizon, p, known_ts) VALUES(?,?,?,?,?,?,?,?)",
                            rows)
        try:     # Block 16: the frozen forecast card (scenario, counter-scenario, invalidation, data quality, version)
            nc = await asyncio.to_thread(cards.freeze, self.db, max(now, time.time()), "strateq", data, how, facts,
                                         STRATEGIST_SYSTEM, self._chain(trigger) if trigger else "saatlıq")
            self._rep("cards", "done", note=f"{nc} proqnoz kartı donduruldu")
        except Exception as e:   # a card that cannot be written never loses the forecast itself
            log.warning("forecast card: %s", e)
            self._rep("cards", "error", note=f"{type(e).__name__}: {str(e)[:100]}")
        from . import checker
        self.db.script(checker.SCHEMA)
        chk = self.db.execute("SELECT invented FROM brain_checks WHERE slot='strategist' ORDER BY ts DESC LIMIT 1").fetchone()
        if chk is not None:
            self._rep("checker", "done", note="Strateqin son cavabı: " + (
                f"{chk['invented']} uydurma rəqəm (göstərilmədi)" if chk["invented"] else "uydurma rəqəm yoxdur"))
        # 27.11 (plan 3.3, owner approved): the second analyst and the debate (both on the «analyst2» slot, 36 $ of
        # the month's 89 $) showed no edge over chance in 383 and 93 views; they run every 4 hours, not every hour
        if self._round_due("analyst2", now):
            await self.second_brain(now, facts, trigger)
        if self._round_due("debate", now):
            await self.debate(now, facts, trigger)
        await self.chartist(now, trigger)
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
                    tag = (self._chain(trigger) + " · ") if trigger else ""
                    rows.append((now, source, m["symbol"], lean, f"{tag}{how} · {str(m.get('why', ''))[:200]}", h, p,
                                 max(now, time.time())))   # known_ts: when the answer arrived, not when it was asked
        return rows

    async def sleep(self, now: float) -> int:
        """The nightly review (Block 11): calibration, then at most 3 lessons from the day's biggest brain errors."""
        from . import learning
        await asyncio.to_thread(learning.calibrate, self.db, now)
        errors = await asyncio.to_thread(learning.day_errors, self.db, now)
        self.db.script(learning.LESSONS_SCHEMA)
        self.db.execute("UPDATE lessons SET active=0 WHERE ts < ?", (now - 7 * 86400,))
        self.db.script(learning.PROPOSALS_SCHEMA)
        await asyncio.to_thread(learning.judge_proposals, self.db, now)   # decided every night, quiet or not
        if learning.LESSONS_OFF:     # owner 2026-11-26: no effect in 526 cases (44.5 % vs 44.9 %) -> no brain spend
            self.db.execute("UPDATE lessons SET active=0")
            self.db.put("sleep:last", json.dumps({"ts": now, "errors": len(errors), "lessons": 0,
                                                  "note": "gecə dərsləri dayandırılıb (sahibin qərarı)"}))
            return 0
        if len(errors) < 2:
            self.db.put("sleep:last", json.dumps({"ts": now, "errors": len(errors), "lessons": 0}))
            return 0
        data, how = await brains.run(self.db, self.keys, "reviewer", learning.LESSON_SYSTEM,
                                     "Errors (JSON):\n" + json.dumps(errors, ensure_ascii=False),
                                     learning.LESSON_SCHEMA_JSON, max_tokens=800)
        lessons = [str(x)[:240] for x in (data or {}).get("lessons", [])][:3]
        facts = json.dumps(errors, ensure_ascii=False)
        lessons = [guard_numbers(x, facts) for x in lessons]
        self.db.executemany("INSERT INTO lessons(ts, text) VALUES(?,?)", [(now, x) for x in lessons if x.strip()])
        # Block 29: each lesson is also a rule proposal — tested (A/B by day on the second analyst) before it counts
        self.db.executemany("INSERT INTO rule_proposals(ts, text, status) VALUES(?,?,?)",
                            [(now, x, "sınaqda (A/B, 7 gün)") for x in lessons if x.strip()])
        self.db.put("sleep:last", json.dumps({"ts": now, "errors": len(errors), "lessons": len(lessons), "brain": how}))
        self._rep("strateq", "done", note=f"gecə yoxlaması: {len(errors)} səhv → {len(lessons)} dərs")
        return len(lessons)

    async def debate(self, now: float, facts: str, trigger) -> bool:
        """Bull and bear argue (the second analyst's brain, cheap), the reviewer brain judges (another company)."""
        if not (self.keys.first(brains.config(self.db, "analyst2")["provider"])
                and self.keys.first(brains.config(self.db, "reviewer")["provider"])):
            return False
        self._rep("debate", "working", "W1 Yuxarı tərəfdarı", 0.2, self._chain(trigger))
        bull, _ = await brains.run(self.db, self.keys, "analyst2", BULL_SYSTEM, "Facts (JSON):\n" + facts,
                                   CASE_SCHEMA, max_tokens=4000)
        self._rep("debate", "working", "W2 Aşağı tərəfdarı", 0.5, self._chain(trigger))
        bear, _ = await brains.run(self.db, self.keys, "analyst2", BEAR_SYSTEM, "Facts (JSON):\n" + facts,
                                   CASE_SCHEMA, max_tokens=4000)
        if bull is None or bear is None:
            self._rep("debate", "error", note="tərəfdarlardan biri cavab vermədi")
            return False
        self._rep("debate", "working", "W3 Hakim beyin", 0.8, self._chain(trigger))
        user = ("Facts (JSON):\n" + facts + "\n\nBULL case:\n" + json.dumps(bull, ensure_ascii=False) +
                "\n\nBEAR case:\n" + json.dumps(bear, ensure_ascii=False))
        data, how = await brains.run(self.db, self.keys, "reviewer", DEBATE_JUDGE_SYSTEM, user, ANALYST2_SCHEMA,
                                     max_tokens=4000)
        if data is None:
            self._rep("debate", "error", note="hakim beyin cavab vermədi: " + how)
            return False
        rows = self._prob_rows(now, "debate", data, how, trigger)
        self.db.executemany("INSERT INTO brain_views(ts, source, metal, lean, note, horizon, p, known_ts) VALUES(?,?,?,?,?,?,?,?)",
                            rows)
        self.db.put("debate:last", json.dumps({"ts": now, "bull": bull, "bear": bear, "judge": data, "brain": how},
                                              ensure_ascii=False))
        self._rep("debate", "done", note=f"{len(rows)} ehtimal · {how}")
        return True

    async def chartist(self, now: float, trigger=None) -> bool:
        """Block 23: the Chartist reads the charts itself (three timeframes, levels, indicators) and gives its own
        1 h / 4 h / 1 day probabilities; stored apart (source «chartist») and judged like every analyst."""
        if not self.keys.first(brains.config(self.db, "chartist")["provider"]):
            return False
        self._rep("chartist", "working", "W1 Şamlar", 0.1, self._chain(trigger))
        charts = await asyncio.to_thread(chart_facts, self.db, now)
        self._rep("chartist", "working", "W2 Beyin", 0.4)
        data, how = await brains.run(self.db, self.keys, "chartist", CHARTIST_SYSTEM, "Charts (JSON):\n" + charts,
                                     CHARTIST_SCHEMA, max_tokens=5000)
        if data is None:
            self._rep("chartist", "error", note="cavab gəlmədi: " + how)
            return False
        rows = self._prob_rows(now, "chartist", data, how, trigger)
        brainviews.ensure(self.db)
        self.db.executemany("INSERT INTO brain_views(ts, source, metal, lean, note, horizon, p, known_ts) "
                            "VALUES(?,?,?,?,?,?,?,?)", rows)
        clean = [{k: (guard_numbers(str(m.get(k, "")), charts) if k in ("trend", "levels", "pattern", "why") else m.get(k))
                  for k in ("symbol", "trend", "levels", "pattern", "p1h", "p4h", "p1d", "why")}
                 for m in data.get("metals", []) if m.get("symbol") in ("XAU", "XAG", "XPT", "XPD")]
        self.db.put("chartist:last", json.dumps({"ts": now, "brain": how, "metals": clean}, ensure_ascii=False))
        try:      # its forecasts are frozen as cards too (with the rules it cited), so its record is kept per rule
            await asyncio.to_thread(cards.freeze, self.db, max(now, time.time()), "chartist", data, how, charts,
                                    CHARTIST_SYSTEM, self._chain(trigger))
        except Exception as e:
            log.warning("chartist card: %s", e)
        self._rep("chartist", "done", note=f"{len(rows)} ehtimal · {how}")
        return True

    def _round_due(self, name: str, now: float) -> bool:
        """Once per SECOND_EVERY for the second analyst and the debate (kept across restarts)."""
        if now - float(self.db.get(f"round:{name}") or 0) < SECOND_EVERY:
            return False
        self.db.put(f"round:{name}", str(now))
        return True

    @staticmethod
    def _chain(trigger) -> str:
        return ("həyəcan #" + ",".join(str(a["id"]) for a in trigger)) if trigger else "saatlıq"

    async def second_brain(self, now: float, facts: str, trigger) -> bool:
        """The same facts to a brain of another company, which never sees the Strategist's answer."""
        if not self.keys.first(brains.config(self.db, "analyst2")["provider"]):
            return False
        from . import learning
        lessons = learning.active_lessons(self.db, now) if learning.lessons_today(self.db, now) else []
        extra = ("\n\nLessons from this desk's past errors (consider them, they are not facts):\n- " +
                 "\n- ".join(lessons)) if lessons else ""
        data, how = await brains.run(self.db, self.keys, "analyst2", ANALYST2_SYSTEM, "Facts (JSON):\n" + facts + extra,
                                     ANALYST2_SCHEMA, max_tokens=4000)
        if data is None:
            self._state("analyst2", "alınmadı: " + how)
            return False
        rows = self._prob_rows(now, "brain2", data, how, trigger)
        self.db.executemany("INSERT INTO brain_views(ts, source, metal, lean, note, horizon, p, known_ts) VALUES(?,?,?,?,?,?,?,?)",
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
        self.reporter.activity = self.activity
        try:
            n = await self.reporter.tick(now)
            if n:
                self._state("reporter", f"{n} bazar rəqəmi tapıldı və iki beyin təsdiqlədi")
        except Exception:
            log.exception("reporter failed")
        try:
            from . import ideas
            n = await ideas.tick(self.db, self.keys, now, self.activity)
            if n:
                self._state("ideas", f"{n} yeni fikir Hakimin sınağına göndərildi")
        except Exception:
            log.exception("ideas failed")
        if now >= self.next_scout and self.feeds is not None:
            # plan 27.11 step 7.1: no more routine search every 4 hours — every 30 minutes around a high-impact US
            # release, and at once on a news alarm (below, at most SCOUT_ALARMS_PER_DAY); the routine headlines
            # come from the feeds
            from .engine import market_open
            hot = self.feeds.event_mode(now) is not None
            self.next_scout = now + (SCOUT_EVENT_EVERY if hot else 15 * 60)
            if hot and market_open(now) and self.keys.first("xai"):
                self._rep("scout", "working", note="X-də axtarır")
                n = await self.scout(now)
                self._rep("scout", "done" if n else "error", note=self.state("scout").get("message", ""))
        if now >= self.next_reader:
            self.next_reader = now + READER_EVERY
            self._rep("reader", "working", note="başlıqlar qiymətləndirilir")
            n = await self.reader(now)
            self._rep("reader", "done", note=f"{n} başlıq" if n else self.state("reader").get("message", "yeni başlıq yoxdur"))
        # the nightly review (sleep): 06:00 UTC, once a day
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if time.gmtime(now).tm_hour == SLEEP_HOUR_UTC and self.db.get("sleep:day") != day:
            self.db.put("sleep:day", day)
            try:
                await self.sleep(now)
                heartbeat.beat("learning-nightly", "ok", "gecə icmalı")
            except Exception as e:
                log.exception("sleep review failed")
                heartbeat.beat("learning-nightly", "fail", type(e).__name__)
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
        if alarm and all(a["kind"] == "move" for a in alarm) and count.get("move", 0) >= signals.MOVE_ALARMS_PER_DAY:
            signals.mark(self.db, [a["id"] for a in alarm], now)    # moves alone: today's share is used up
            alarm = []
        if alarm:
            self._rep("signals", "working", note=f"{len(alarm)} siqnal: " + alarm[0]["text"][:100])
        if alarm and now - float(self.db.get("alarm:last") or 0) >= ALARM_GAP and count["n"] < ALARMS_PER_DAY:
            self.db.put("alarm:last", str(now))
            count["n"] += 1
            if all(a["kind"] == "move" for a in alarm):
                count["move"] = count.get("move", 0) + 1
            # a strong headline or (27.11, plan 8.1) a price spike: the scout looks for the cause on X at once,
            # at most SCOUT_ALARMS_PER_DAY a day
            if any(a["kind"] in ("news", "move") for a in alarm) and count["scout"] < SCOUT_ALARMS_PER_DAY \
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
            self._rep("signals", "done", note=self._chain(alarm) + " işləndi")
        elif now >= self.next_strategist:
            from . import nerve
            alarmed = nerve.state(self.db).get("state") == "HƏYƏCAN"
            every = (STRATEGIST_EVERY // 2 if alarmed else STRATEGIST_EVERY) * brains.pace(self.db, "strategist", now)
            self.next_strategist = now + every
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
