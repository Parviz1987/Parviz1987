"""The running heart of TST Trade: polls prices, builds candles, issues forecasts at every candle close, has the
Judge score them, and backfills history (Twelve Data key) for the longer horizons."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import heartbeat
from . import brainviews, candles, registry, forecast, judge, markets, rules, slowviews, surprise, unified
from .db import DB
from .keys import KeyStore
from .providers.base import NotServed, ProviderError, Quote
from .providers.capital import CapitalHistory, CapitalStream
from .providers.demo import DemoHistory, DemoPrices
from .providers.goldapi import GoldApiProvider
from .providers.twelvedata import TwelveDataHistory, TwelveDataPrices

log = logging.getLogger("tst.engine")
HISTORY_EVERY = 6 * 3600
BACKUP_HOUR_UTC = 7         # 02:00 New York: the quietest hour
JOBS_EVERY = 15             # seconds between brain-job checks (reader, signals, alarms, scout, strategist)
HISTORY_LIMIT = {"1m": 1500, "15m": 4000, "30m": 4000, "1h": 4000, "4h": 3000, "1d": 2000, "1w": 600}
BACKTEST_MAX = 4000
TICK_KEEP = 3 * 86400
MINUTE_KEEP = 30 * 86400


_NY = ZoneInfo("America/New_York")


def market_open(ts: float) -> bool:
    """Spot metals trade almost 24/5, on New York time (owner 2026-11-26; the old UTC hours were right in summer only):
    Sunday 18:00 to Friday 17:00 New York, with a daily break 17:00-18:00 New York. In winter that is Sunday 23:00 -
    Friday 22:00 UTC with the break 22:00-23:00 UTC; in summer one hour earlier. Exchange holidays are not modelled."""
    d = datetime.fromtimestamp(ts, _NY)
    wd, h = d.weekday(), d.hour
    if wd == 5:
        return False
    if wd == 6:
        return h >= 18
    return h != 17 and not (wd == 4 and h >= 17)


target_time = forecast.target_time   # kept here for older imports


UNIFIED_EVERY = 6 * 3600       # the unified forecast's walk-forward self-simulation


def decision_time(issued_t: int, tf: str) -> int:
    """When a forecast for the candle labelled issued_t is really made: daily and weekly candles open at 22:00 UTC
    the evening before their label (candles.SESSION_SHIFT); intraday candles at their label."""
    return issued_t - candles.SESSION_SHIFT if tf in ("1d", "1w") else issued_t


class MacroLookup:
    """FRED values as they were known when a daily forecast was issued (22:00 UTC the evening before its candle).
    DFII10 for a day is published the next afternoon; the broad dollar index (H.10) comes out weekly on Monday for the
    week before. So a candle labelled D may use DFII10 up to D-2 and the dollar index up to D-10."""
    LAG_DAYS = {"DFII10": 2, "DTWEXBGS": 10}
    def __init__(self, db: DB):
        self.series = {}
        for sid in ("DFII10", "DTWEXBGS"):
            try:
                rows = db.execute("SELECT d, v FROM macro WHERE series=? ORDER BY d", (sid,)).fetchall()
            except Exception:
                rows = []
            try:     # Block 18: where ALFRED gave the first published value of a day, it replaces the revised one
                first = {r["d"]: r["v"] for r in db.execute("SELECT d, v FROM macro_first WHERE series=?",
                                                            (sid,)).fetchall()}
            except Exception:
                first = {}
            self.series[sid] = ([r["d"] for r in rows], [first.get(r["d"], r["v"]) for r in rows])

    def first_day(self) -> str | None:
        firsts = [ds[0] for ds, _ in self.series.values() if ds]
        return max(firsts) if len(firsts) == len(self.series) else None

    def _change(self, sid: str, day: str, pct: bool) -> float | None:
        import bisect
        ds, vs = self.series[sid]
        i = bisect.bisect_left(ds, day) - 1        # last value strictly before the day
        if i < 5:
            return None
        a, b = vs[i - 5], vs[i]
        return (b / a - 1) * 100 if pct else b - a

    def at(self, t: int) -> dict | None:
        def day(sid: str) -> str:   # first day NOT yet known: values strictly before it may be used
            return datetime.fromtimestamp(t - (self.LAG_DAYS[sid] - 1) * 86400, timezone.utc).strftime("%Y-%m-%d")
        r, d = self._change("DFII10", day("DFII10"), False), self._change("DTWEXBGS", day("DTWEXBGS"), True)
        return None if r is None or d is None else {"dfii10": r, "dollar": d}


class GvzLookup:
    """GVZ (FRED GVZCLS, gold options' expected volatility) as known before a daily candle (published the next day)."""
    def __init__(self, db: DB):
        try:
            rows = db.execute("SELECT d, v FROM macro WHERE series='GVZCLS' ORDER BY d").fetchall()
        except Exception:
            rows = []
        self.ds, self.vs = [r["d"] for r in rows], [r["v"] for r in rows]

    def at(self, t: int) -> float | None:
        import bisect
        day = datetime.fromtimestamp(t - 86400, timezone.utc).strftime("%Y-%m-%d")
        i = bisect.bisect_left(self.ds, day) - 1
        return self.vs[i] if i >= 0 else None


PAIR = {"XAU": "XAG", "XAG": "XAU", "XPT": "XPD", "XPD": "XPT"}


class BondLookup:
    """The 10-year Treasury note's 12-month price change as known before a time (daily candles, past only)."""
    def __init__(self, db: DB):
        import bisect as _b
        self._b = _b
        rows = db.execute("SELECT t, c FROM candles WHERE symbol='US10Y' AND tf='1d' ORDER BY t").fetchall()
        self.ts = [r["t"] for r in rows]
        self.cs = [r["c"] for r in rows]

    def at(self, t: float) -> float | None:
        i = self._b.bisect_left(self.ts, t - 86400) - 1      # the last daily candle that had closed by t
        if i < forecast.TSMOM_DAYS:
            return None
        return self.cs[i] / self.cs[i - forecast.TSMOM_DAYS] - 1


class EventLookup:
    """Times of high-impact US releases (Forex Factory schedule). A forecast issued from 30 minutes after a release
    back to 60 minutes before one is "near an event": the selective consensus stays silent there."""
    def __init__(self, db: DB):
        import bisect as _b
        self._b = _b
        try:
            self.ts = [r["ts"] for r in db.execute("SELECT ts FROM events WHERE country='USD' AND impact='High' "
                                                    "ORDER BY ts").fetchall()]
        except Exception:
            self.ts = []

    def near(self, t: float) -> bool:
        i = self._b.bisect_left(self.ts, t - 1800)
        return i < len(self.ts) and self.ts[i] <= t + 3600


class Engine:
    def __init__(self, db: DB, keys: KeyStore, default_provider: str, poll_seconds: int, feeds=None, jobs=None):
        self.db = db
        self.feeds = feeds
        self.jobs = jobs
        self.keys = keys
        self.default_provider = default_provider
        self.poll = poll_seconds
        self.provider = None
        self.provider_name = None
        self.quotes: dict[str, dict] = {}
        self.errors: dict[str, str] = {}
        self.last_poll: float | None = None
        self.last_ok: float | None = None
        self._weights_cache: dict = {}
        self._issued: set = set()          # (horizon, metal, issued_t) already issued live
        from .liquidity import Liquidity
        self.liquidity = Liquidity()           # the liquidity agent: spread and activity per metal, from the stream
        from .nerve import Reflex
        self.reflex = Reflex()                 # the reflex: a sudden jump closes the metal at once, no brain asked
        self._weights_ts = 0.0
        self.decisions: dict = {}
        self.history_state: dict = json.loads(db.get("history_state") or "{}")
        self._macro_cache = None
        self.activity = None      # app.activity.Hub, set by the app: where this agent reports its status
        self._rel_written: dict[str, float] = {}
        self._rel_cache = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ---------- price source ----------
    fallback_until = 0.0        # the repair catalogue's price_fallback: gold-api.com until this time (repair.py)

    def chosen_provider(self) -> str:
        if self.fallback_until and time.time() < self.fallback_until:
            return "goldapi"
        return self.db.get("setting:price_provider") or self.default_provider

    def _make_provider(self):
        name = self.chosen_provider()
        if name == "twelvedata":
            key = self.keys.first("twelvedata")
            if not key:
                self.errors = {"*": "Twelve Data seçilib, amma açar saxlanmayıb: gold-api.com işləyir"}
                return GoldApiProvider(), "goldapi"
            return TwelveDataPrices(key), "twelvedata"
        if name == "capital":
            creds = self.keys.get("capital")
            if not creds:
                self.errors = {"*": "Capital.com seçilib, amma açar saxlanmayıb: gold-api.com işləyir"}
                return GoldApiProvider(), "goldapi"
            return CapitalStream(creds, on_quote=self.on_quote,
                                 extra=markets.saved(self.db).get("epics")), "capital"
        if name == "demo":
            return DemoPrices(), "demo"
        return GoldApiProvider(), "goldapi"

    async def _ensure_provider(self) -> None:
        if self.provider is None or self.provider_name != self.chosen_provider():
            if self.provider is not None:
                await self.provider.aclose()
            self.provider, self.provider_name = self._make_provider()

    def reset_provider(self) -> None:
        self.provider_name = None   # rebuilt at the next poll (a new key or a new choice)

    def on_quote(self, q: Quote) -> None:
        """A streamed price: stored the moment it arrives (no wait for the next poll). Related markets (dollar,
        oil...) quote many times a second: they are written at most once a second each (candles only, no ticks)."""
        now = time.time()
        self.quotes[q.symbol] = {"price": q.price, "source_ts": q.source_ts, "recv_ts": now,
                                 "ts_missing": q.source_ts_missing}
        if q.symbol not in candles.METALS:
            if now - self._rel_written.get(q.symbol, 0) >= 1.0:
                self._rel_written[q.symbol] = now
                candles.add_tick(self.db, q.symbol, now, q.price)
            return
        self.db.execute("INSERT INTO ticks(symbol, ts, price, source, source_ts) VALUES(?,?,?,?,?)",
                        (q.symbol, now, q.price, "capital", q.source_ts))
        candles.add_tick(self.db, q.symbol, now, q.price)
        self.liquidity.add(q.symbol, now, q.bid, q.ask)
        self.reflex.feel(q.symbol, now, q.price)
        self.last_ok = now

    async def poll_once(self, now: float | None = None) -> None:
        await self._ensure_provider()
        now = time.time() if now is None else now
        self.last_poll = now
        try:
            quotes, errors = await self.provider.fetch(list(candles.METALS))
        except ProviderError as e:
            quotes, errors = [], {"*": str(e)}
        self.errors = errors
        if self.provider_name == "capital":
            return   # the stream stores every quote itself (on_quote); the poll only reads its health
        for q in quotes:
            self.quotes[q.symbol] = {"price": q.price, "source_ts": q.source_ts, "recv_ts": now,
                                     "ts_missing": q.source_ts_missing}
            if not market_open(now):
                continue                  # a closed market's repeated price is not a candle (no weekend candles)
            self.db.execute("INSERT INTO ticks(symbol, ts, price, source, source_ts) VALUES(?,?,?,?,?)",
                            (q.symbol, now, q.price, self.provider_name, q.source_ts))
            candles.add_tick(self.db, q.symbol, now, q.price)
            self.liquidity.add(q.symbol, now, q.bid, q.ask)
        if quotes:
            self.last_ok = now

    def status(self, symbol: str, now: float | None = None) -> str:
        now = time.time() if now is None else now
        if self.provider_name == "demo":
            return "DEMO"
        q = self.quotes.get(symbol)
        if q is None or now - q["recv_ts"] > 3 * self.poll + 10:
            return "OFFLINE"
        if q["ts_missing"] or now - q["source_ts"] > 120:
            return "DELAYED"
        return "LIVE"

    def shown_status(self, symbol: str, now: float | None = None) -> str:
        """What the owner sees. A quiet feed while the market is closed (weekend, daily break) is «CLOSED», not
        «OFFLINE»: owner 27.11 22:28 read «Əlaqə yoxdur» on a Friday night as a broken Capital.com link.
        Internal logic keeps using status()."""
        now = time.time() if now is None else now
        st = self.status(symbol, now)
        return "CLOSED" if st == "OFFLINE" and self.provider_name != "demo" and not market_open(now) else st

    def _macro(self, now: float) -> "MacroLookup":
        """FRED data changes a few times a day: the lookup is rebuilt at most once an hour, not at every poll."""
        if self._macro_cache is None or now - self._macro_cache[0] > 3600:
            self._macro_cache = (now, MacroLookup(self.db))
        return self._macro_cache[1]

    def _releases(self, now: float) -> "surprise.Lookup":
        """US releases change when a figure comes out: rebuilt every minute (cheap, a few thousand rows)."""
        if self._rel_cache is None or now - self._rel_cache[0] > 60:
            self._rel_cache = (now, surprise.Lookup(self.db))
        return self._rel_cache[1]

    def migrate(self) -> None:
        """Once per start: daily candles labelled Saturday or Sunday came from the old bucketing (Sunday-evening
        ticks before the session shift); the forecasts issued on them over a weekend are duplicates."""
        self.db.execute("DELETE FROM candles WHERE tf='1d' AND strftime('%w', t, 'unixepoch') IN ('0', '6')")
        self.db.execute("DELETE FROM forecasts WHERE horizon IN ('1d', '3d', '10d', '1mo') "
                        "AND strftime('%w', issued_t, 'unixepoch') IN ('0', '6')")
        try:
            judge.set_swap(json.loads(self.db.get("swap_rates") or "{}").get("rates", {}))
        except (ValueError, AttributeError):
            pass
        sig = ",".join(forecast.METHODS)
        if self.db.get("methods_sig") != sig:
            # A new forecast method: the history is replayed now for it (old forecasts stay as issued).
            self.history_state["ts"] = 0
            self.db.put("methods_sig", sig)
        if not self.db.get("futures:daily_approved"):
            # The owner's decision (chat, 2026-11-25, «buna icazə verirəm»): top up the COMEX futures bars every day
            # (about 0.35 $ a month from the Databento free credit), hard ceiling futures.DAILY_CAP_USD a month.
            from . import futures as fut
            self.db.put("futures:daily_approved", json.dumps(
                {"ts": time.time(), "cap_usd_month": fut.DAILY_CAP_USD,
                 "by": "sahib, Claude ilə çatda 2026-11-25 (ayda ~0,35 $, pulsuz kreditdən)"}, ensure_ascii=False))
        if not self.db.get("migr:futdaily_fix_1125") and not self.db.get("futures:daily_last"):
            # the first daily top-ups were refused (asked past Databento's history end) but their quote was counted as
            # spent: nothing was delivered, so nothing was billed
            self.db.execute("DELETE FROM kv WHERE k LIKE 'futures:daily_spent:%'")
            self.db.put("migr:futdaily_fix_1125", "1")
        if not self.db.get("migr:ideas3_1125"):
            # The owner's decision (chat, 2026-11-25, «1-2 ed»): the new «Fərziyyə agenti» slot, monthly limit 3 $.
            from . import brains as brain_cfg
            brain_cfg.save(self.db, "ideas", {"month_usd": 3})
            self.db.put("migr:ideas3_1125", "1")
        if not self.db.get("migr:agents_gemini_1126"):
            # The owner's decision (chat, 2026-11-26: «the idle APIs should be used»): the data agents search with
            # Gemini (Google Search) and OpenAI (web search), two companies; the 10 $ monthly limit stays.
            from . import brains as brain_cfg
            brain_cfg.save(self.db, "reporter", {"provider": "gemini", "model": "gemini-2.5-flash",
                                                 "fallback": "openai", "fallback_model": "gpt-5.4-nano"})
            self.db.put("migr:agents_gemini_1126", "1")
        if not self.db.get("migr:reporter10_1125"):
            # The owner's decision (chat, 2026-11-25): the new «Bazar müxbiri» slot gets a 10 $ monthly limit.
            from . import brains as brain_cfg
            brain_cfg.save(self.db, "reporter", {"month_usd": 10})
            self.db.put("migr:reporter10_1125", "1")
        if not self.db.get("migr:limits50_1125"):
            # The owner's decision (chat, 2026-11-25): every brain's monthly limit 50 $. The counted cost of Grok and
            # the OpenAI nano model uses a deliberately high default price, so a 20 $ cap could stop them although
            # the real bill is lower; real prices are to be compared with the providers' bills after 4-5 days.
            from . import brains as brain_cfg      # (registry is imported at module level: no local name here)
            for slot in registry.BRAIN_IDS - {"reporter", "ideas"}:      # the reporter's own limit is 10 $ (owner, below)
                if float(brain_cfg.config(self.db, slot)["month_usd"]) < 50:
                    brain_cfg.save(self.db, slot, {"month_usd": 50})
            self.db.put("migr:limits50_1125", "1")
        if not self.db.get("migr:audit_1124"):
            # Audit 2026-11-24, honest history: (1) daily-candle forecasts used news and brain views up to 2 h after
            # they were made — those methods are replayed with the right time; (2) the replay issued intraday
            # forecasts right after the daily break, which live never does — those moments are removed.
            daily = ("1d", "3d", "10d", "1mo", "1w")
            self.db.execute(f"DELETE FROM forecasts WHERE mode='history' AND horizon IN ({','.join('?' * len(daily))}) "
                            "AND method IN ('news','strateq','brain2','debate','chartist','consensus')", daily)
            for h, tf in forecast.HORIZONS.items():
                if tf in ("1d", "1w"):
                    continue
                step = candles.TF[tf]
                for sym in candles.METALS:
                    ts = [r["t"] for r in self.db.execute("SELECT t FROM candles WHERE symbol=? AND tf=? ORDER BY t",
                                                          (sym, tf)).fetchall()]
                    bad = [(sym, h, b) for a, b in zip(ts, ts[1:]) if b - a != step]
                    self.db.executemany("DELETE FROM forecasts WHERE mode='history' AND symbol=? AND horizon=? "
                                        "AND issued_t=?", bad)
            self.history_state["ts"] = 0          # the replay refills what was removed, the honest way
            self.db.put("migr:audit_1124", "1")
        if not self.db.get("migr:alarm_count_reset_1124"):
            # 9 of the 12 alarms of 2026-11-24 (UTC) went to ordinary moves before the move cap existed (9f897e5):
            # the day's count starts again once, so today's news and figures still get their alarms.
            self.db.put("alarm:count", "{}")
            self.db.put("migr:alarm_count_reset_1124", "1")
        if not self.db.get("migr:cheaper_brains_v1"):
            # Block 12: a slot still on the old default moves to the new, cheaper default (an owner's own choice stays).
            for slot, old in (("reader", ("openai", "gpt-5.4-nano")), ("strategist", ("anthropic", "claude-opus-5-5"))):
                raw = self.db.get(f"brain:{slot}")
                if raw:
                    cfg = json.loads(raw)
                    if (cfg.get("provider"), cfg.get("model")) == old:
                        base = next(b for b in registry.BRAIN_SLOTS if b["id"] == slot)
                        cfg.update({k: base[k] for k in ("provider", "model", "fallback", "fallback_model")})
                        self.db.put(f"brain:{slot}", json.dumps(cfg))        # the owner's limit is kept
            self.db.put("migr:cheaper_brains_v1", "1")
        if not self.db.get("migr:history_pages_v2"):
            # Capital's older pages are now asked within 1000 candle slots: loaded and replayed once now.
            self.history_state["ts"] = 0
            self.db.put("migr:history_pages_v2", "1")
        if not self.db.get("migr:history_4000"):
            # Longer history (pages walked back at the broker): loaded and replayed once now, not in 6 hours.
            self.history_state["ts"] = 0
            self.db.put("migr:history_4000", "1")
        if not self.db.get("migr:selective_v1"):
            # The consensus became selective (families, event and volatility gates): its history is replayed once.
            self.db.execute("DELETE FROM forecasts WHERE mode='history' AND method='consensus'")
            self.history_state["ts"] = 0
            self.db.put("migr:selective_v1", "1")
        if not self.db.get("migr:dollar_pick_v1"):
            # The dollar impulse now picks the dollar market most linked to the metal: replayed once.
            self.db.execute("DELETE FROM forecasts WHERE mode='history' AND method='dollar'")
            self.history_state["ts"] = 0
            self.db.put("migr:dollar_pick_v1", "1")
        if not self.db.get("migr:no_1m_desk"):
            # The one-minute desk was removed: its history replay goes (derived data); its live results stay
            # until the normal 30-day clean-up, as the record of why it was removed.
            self.db.execute("DELETE FROM forecasts WHERE horizon='1m' AND mode='history'")
            self.db.execute("DELETE FROM forecasts WHERE horizon='1m' AND scored_ts IS NULL")
            self.history_state["ts"] = 0      # 15- and 30-minute history is loaded and replayed at once
            self.db.put("migr:no_1m_desk", "1")
        if not self.db.get("migr:ranges_v2"):
            # Ranges now take their width from past move/volatility ratios. History forecasts are derived data:
            # replayed once so the Judge's range coverage describes the ranges in use. Live forecasts stay.
            self.db.execute("DELETE FROM forecasts WHERE mode='history'")
            self.history_state["ts"] = 0
            self.db.put("migr:ranges_v2", "1")
            self.db.put("migr:macro_lag_v1", "1")
        if not self.db.get("migr:macro_lag_v1"):
            # Replayed before the publication lags were respected: dropped once and replayed at once.
            self.db.execute("DELETE FROM forecasts WHERE mode='history' AND method='macro'")
            self.history_state["ts"] = 0
            self.db.put("migr:macro_lag_v1", "1")

    # ---------- forecasts ----------
    def issue_due(self, now: float | None = None, mode: str = "live") -> int:
        """At each candle close: one forecast per horizon, metal and method, for the close k candles ahead."""
        now = time.time() if now is None else now
        n = 0
        macro = self._macro(now)
        rel = self._releases(now)
        bv = brainviews.Lookup(self.db)
        sv = slowviews.Lookup(self.db)
        rl = rules.live_lookup(self.db)
        fl = rules.live_lookup(self.db, "fa")
        cl = rules.live_lookup(self.db, "cm")
        tl = rules.live_lookup(self.db, "tm")
        from . import newsblock
        nv = newsblock.live_voice(self.db)
        ev = EventLookup(self.db)
        bonds, gvz = BondLookup(self.db), GvzLookup(self.db)
        for h, tf in forecast.HORIZONS.items():
            issued_t = candles.bucket(now, tf)
            step = candles.TF[tf]
            # Saturday and Sunday have no daily candle: nothing is issued for them (the Monday forecast follows
            # Friday's candle). Without this the same target would be forecast three times over a weekend.
            if tf == "1d" and datetime.fromtimestamp(issued_t, timezone.utc).weekday() >= 5:
                continue
            for sym in candles.METALS:
                past = candles.closed(self.db, sym, tf, now, limit=forecast.history_need(h))
                if not past:
                    continue
                # Only right after a real candle: a closed market or a feed gap issues nothing. Monday's daily
                # forecast follows Friday's candle.
                gap = issued_t - past[-1]["t"]
                monday = tf == "1d" and datetime.fromtimestamp(issued_t, timezone.utc).weekday() == 0
                if gap != step and not (monday and gap == 3 * step):
                    continue
                if (h, sym, issued_t) in self._issued:
                    continue                     # already issued this candle (INSERT OR IGNORE would drop it anyway)
                # a daily candle labelled D starts at 22:00 UTC the evening before: that is when the forecast is made
                # and the latest moment whose news and brain views it may use (audit 2026-11-24: 2 h look-ahead)
                known = decision_time(issued_t, tf)
                try:
                    linked_now = {"bond": bonds.at(issued_t),
                                  "gvz": gvz.at(issued_t) if tf in ("1d", "1w") and sym == "XAU" else None}
                    fc = forecast.build(past, h, macro.at(issued_t) if tf == "1d" else None, issued_t,
                                        rel.window(issued_t, h), linked_now,
                                        {**bv.views(sym, known, h), **sv.views(sym, issued_t, h),
                                         **rl.views(sym, known, h), **fl.views(sym, known, h), **nv.views(sym, known, h),
                                         **cl.views(sym, known, h), **tl.views(sym, known, h),
                                         "_weights": self.weights(sym, h, now) if mode == "live" else None,
                                         "_unified": unified.models(self.db).get(f"{sym}:{h}") if mode == "live" else None},
                                        ev.near(known))
                except Exception:        # one desk failing must never stop the others or the rest of the cycle
                    log.exception("forecast %s %s failed", sym, h)
                    continue
                if fc is None:
                    continue
                n += judge.issue(self.db, sym, h, issued_t, target_time(issued_t, h), fc, mode)
                if mode == "live":           # the data this forecast saw, fingerprinted (Radar Gold: snapshot ID)
                    try:
                        from . import rigor
                        rigor.snapshot(self.db, sym, h, issued_t, past, fc)
                    except Exception:
                        log.exception("snapshot %s %s", sym, h)
                self._issued.add((h, sym, issued_t))
                if len(self._issued) > 5000:
                    self._issued = {x for x in self._issued if x[2] >= issued_t - 40 * 86400}
        return n

    def weights(self, symbol: str, horizon: str, now: float | None = None) -> dict[str, float]:
        """The scale (tərəzi): the weights last computed by refresh_weights (empty until the first run). Only reads:
        the Judge's queries are heavy and must never run on the event loop (the server must keep answering)."""
        return self._weights_cache.get((symbol, horizon), {})

    def refresh_weights(self) -> None:
        """Off the event loop (a thread), every 10 minutes: each analyst's weight on each desk from the Judge's live
        record once it is long enough (MIN_N), otherwise from the history replay."""
        for symbol in candles.METALS:
            for horizon in forecast.HORIZONS:
                live = judge.stats(self.db, symbol, horizon, "live", ttl=600)
                hist = judge.stats(self.db, symbol, horizon, "history", ttl=600)
                by = {r["method"]: r for r in hist}
                for r in live:
                    if (r.get("nh") or 0) >= judge.MIN_N[horizon]:
                        by[r["method"]] = r             # enough live forecasts: the live record decides
                # Block 11: recent reward-prediction error (Hedge) decides, the long record (z >= 0) vetoes
                from . import learning
                self._weights_cache[(symbol, horizon)] = learning.combine(
                    learning.hedge(self.db, symbol, horizon), list(by.values()), forecast.steps_of(horizon))

    # ---------- history and backtest ----------
    def _history_names(self) -> list[str]:
        if self.chosen_provider() == "demo":
            return ["demo"]
        return [n for n, ok in (("capital", bool(self.keys.get("capital"))),
                                ("twelvedata", bool(self.keys.first("twelvedata")))) if ok]

    def _history_sources(self) -> list:
        """Capital.com first (same broker as the live stream, all four metals, overwrites older history), then
        Twelve Data (free plan: gold only, but deeper daily history) only fills what is still missing."""
        out = []
        for name in self._history_names():
            if name == "demo":
                out.append((DemoHistory(), False))
            elif name == "capital":
                # The live stream's own session is reused: no second login to the broker.
                stream = self.provider if self.provider_name == "capital" else None
                out.append((CapitalHistory(self.keys.get("capital"), stream,
                                           extra=markets.saved(self.db).get("epics")), True))
            else:
                out.append((TwelveDataHistory(self.keys.first("twelvedata")), False))
        return out

    async def _read_swap(self, src) -> None:
        """Block 15: the broker's overnight fees, read with each history load and kept for the Judge's full cost."""
        rates = {}
        for sym in candles.METALS:
            try:
                v = await src.overnight_fee(sym)
            except Exception as e:      # a missing fee leaves the estimate in place; it never stops the history
                log.info("overnight fee %s: %s", sym, e)
                v = None
            if v is not None:
                rates[sym] = v
        if rates:
            self.db.put("swap_rates", json.dumps({"ts": time.time(), "rates": rates}))
            judge.set_swap(rates)

    async def backfill(self, force: bool = False) -> dict:
        now = time.time()
        # A new source (a key just saved, a new version that reads another broker) loads at once, not in 6 hours;
        # at most one such unplanned reload per 5 minutes.
        changed = ", ".join(self._history_names()) != self.history_state.get("source", "")
        age = now - self.history_state.get("ts", 0)
        if not force and (age < 300 or (not changed and age < HISTORY_EVERY)):
            return self.history_state
        sources = self._history_sources()
        if not sources:
            self.history_state = {"ts": now, "result": {}, "note": "Capital.com və ya Twelve Data açarı yoxdur: "
                                  "tarixçə yüklənmir"}
            self.db.put("history_state", json.dumps(self.history_state))
            return self.history_state
        result: dict[str, dict[str, str]] = {}
        related = list(markets.saved(self.db).get("epics", {}))
        self._rep("history", "working", note="tarixçə yüklənir")
        stage_of = {"capital": "W1 Capital", "twelvedata": "W2 Twelve Data", "demo": "W1 Capital"}
        for src, replace in sources:
            try:
                jobs = [(s, tf, lim) for s in candles.METALS for tf, lim in HISTORY_LIMIT.items()]
                if src.name == "capital":   # related markets: only the broker has them
                    jobs += [(s, tf, lim) for s in related for tf, lim in markets.HISTORY_TF.items()]
                refused: set[str] = set()
                for i_job, (sym, tf, limit) in enumerate(jobs):
                    if i_job % 5 == 0:
                        self._rep("history", "working", stage_of.get(src.name, src.name), i_job / max(1, len(jobs)),
                                  f"{sym} {tf}")
                    if sym in refused:
                        continue
                    line = result.setdefault(sym, {})
                    try:
                        rows = await src.candles(sym, tf, limit)
                        candles.store_history(self.db, sym, tf, rows, replace=replace)
                        note = getattr(src, "page_note", "")
                        line[tf] = (line.get(tf, "") + f" {src.name}: {len(rows)} şam" + (f" ({note})" if note else "")).strip()
                    except NotServed as e:
                        line[tf] = (line.get(tf, "") + f" {src.name}: planda yoxdur ({str(e)[:60]})").strip()
                        if src.name == "twelvedata":
                            refused.add(sym)   # the plan serves this symbol on no timeframe
                    except ProviderError as e:
                        line[tf] = (line.get(tf, "") + f" {src.name}: xəta ({str(e)[:80]})").strip()
                    if src.request_gap:
                        await asyncio.sleep(src.request_gap)
            except Exception as e:   # one source failing (login refused...) must not stop the next one
                log.warning("history %s: %s", src.name, e)
                result.setdefault("*", {})[src.name] = f"xəta: {str(e)[:120]}"
            finally:
                if src.name == "capital":
                    await self._read_swap(src)       # Block 15: the broker's overnight fees (never stops the history)
                await src.aclose()
        self.history_state = {"ts": now, "result": result, "source": ", ".join(s.name for s, _ in sources)}
        self.db.put("history_state", json.dumps(self.history_state))
        # The walk-forward replay is CPU work: off the event loop, so prices keep coming in meanwhile.
        try:
            await asyncio.to_thread(self.backtest, now)
            self._rep("history", "done", note="tarixçə və yenidən hesab bitdi")
        except Exception as e:
            self._rep("history", "error", note=f"{type(e).__name__}: {str(e)[:100]}")
            raise
        return self.history_state

    def backtest(self, now: float | None = None) -> int:
        """Walk forward over stored candles: each forecast sees only the candles before it (mode 'history')."""
        now = time.time() if now is None else now
        n = 0
        self._rep("history", "working", "W3 Yenidən hesab", 0.0, "keçmiş üzərində proqnozlar")
        macro = MacroLookup(self.db)
        rel = surprise.Lookup(self.db)
        bv = brainviews.Lookup(self.db)
        bv.calib = {}        # calibration bands come from recent outcomes: never applied to the past (look-ahead)
        sv = slowviews.Lookup(self.db)
        rl = rules.Lookup(self.db)
        fl = rules.fa_lookup(self.db)
        from . import crossmarket
        cl = crossmarket.lookup(self.db)
        from . import timeblock
        tl = timeblock.lookup(self.db)
        from . import newsblock
        nv = newsblock.Voice(self.db)
        ev = EventLookup(self.db)
        bonds, gvz = BondLookup(self.db), GvzLookup(self.db)
        first = macro.first_day()
        if first:
            # Replayed before FRED data arrived: those macro forecasts said "no data". Now that the data covers
            # their dates, they are replayed (only these rows; every other forecast stays as issued).
            start = int(datetime.strptime(first, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) + 14 * 86400
            self.db.execute("DELETE FROM forecasts WHERE mode='history' AND method='macro' AND basis=? AND issued_t>?",
                            ("FRED məlumatı yoxdur", start))
        for i_h, (h, tf) in enumerate(forecast.HORIZONS.items()):
            step = candles.TF[tf]
            self._rep("history", "working", "W3 Yenidən hesab", i_h / len(forecast.HORIZONS), forecast.HORIZON_NAMES[h])
            for sym in candles.METALS:
                rows = candles.closed(self.db, sym, tf, now, limit=BACKTEST_MAX + forecast.MIN_CANDLES)
                k = forecast.steps_of(h)
                batch: list = []
                # Which methods each past moment already has (2026-11-26: a moment counted as replayed by its NUMBER of
                # methods, so new methods that replaced retired ones — «bazarlar», «vaxt» — never got a history).
                # A moment is replayed again only for the methods it lacks; the rows it has never change.
                mf = forecast.methods_for(h)
                have: dict[int, set] = {}
                for r in self.db.iterate("SELECT issued_t, method FROM forecasts WHERE symbol=? AND horizon=? AND "
                                         f"mode='history' AND method IN ({','.join('?' * len(mf))})", (sym, h, *mf)):
                    have.setdefault(r["issued_t"], set()).add(r["method"])
                done = {t for t, ms in have.items() if len(ms) >= len(mf)}
                live_ts = {r["issued_t"] for r in self.db.execute(
                    "SELECT DISTINCT issued_t FROM forecasts WHERE symbol=? AND horizon=? AND mode='live'",
                    (sym, h)).fetchall()}
                for i in range(forecast.MIN_CANDLES, len(rows)):
                    t = rows[i]["t"]
                    if t in done:
                        continue   # replayed before: forecasts never change once issued
                    gap = rows[i]["t"] - rows[i - 1]["t"]
                    monday = tf == "1d" and datetime.fromtimestamp(t, timezone.utc).weekday() == 0
                    if gap != step and not (monday and gap == 3 * step):
                        continue   # the same rule as live: only right after a real candle (audit 2026-11-24)
                    if t in live_ts:
                        continue   # this moment has live forecasts: no history copy of it
                    window = rows[max(0, i - forecast.history_need(h)):i]
                    fc = forecast.build(window, h, macro.at(t) if tf == "1d" else None, t, rel.window(t, h),
                                        {"bond": bonds.at(t),
                                         "gvz": gvz.at(t) if tf in ("1d", "1w") and sym == "XAU" else None},
                                        {**bv.views(sym, decision_time(t, tf), h), **sv.views(sym, t, h),
                                         **rl.views(sym, decision_time(t, tf), h),
                                         **fl.views(sym, decision_time(t, tf), h),
                                         **cl.views(sym, decision_time(t, tf), h),
                                         **tl.views(sym, decision_time(t, tf), h),
                                         **nv.views(sym, decision_time(t, tf), h)},
                                        ev.near(decision_time(t, tf)))
                    if fc is None:
                        continue
                    target = rows[i + k - 1]["t"] + step if i + k - 1 < len(rows) else target_time(t, h)
                    if t in have:          # only what this moment lacks (small batches, nothing old rewritten)
                        fc = {**fc, "methods": {m: v for m, v in fc["methods"].items() if m not in have[t]}}
                    batch += judge.issue_rows(sym, h, t, target, fc, "history")
                # one transaction per metal and horizon (thousands of small commits are slow on a small disk)
                judge.insert(self.db, batch)
                n += len(batch)
        self._rep("history", "working", "W4 Hakim", 0.0, "tarixçə proqnozları yoxlanır")
        judge.score_due(self.db, now)
        return n

    # ---------- loop ----------
    def prune(self, now: float) -> None:
        """Ticks live 3 days; one- and five-minute candles 30 days (the chart only); scored forecasts of the old
        one-minute desk 30 days; 15- and 30-minute forecasts 180 days (the Judge's recent half year). The rest is kept."""
        self.db.execute("DELETE FROM ticks WHERE ts < ?", (now - TICK_KEEP,))
        self.db.execute("DELETE FROM candles WHERE tf IN ('1m', '5m') AND t < ?", (now - MINUTE_KEEP,))
        self.db.execute("DELETE FROM forecasts WHERE horizon IN ('15m', '30m') AND scored_ts IS NOT NULL "
                        "AND target_t < ?", (now - 180 * 86400,))
        self.db.execute("DELETE FROM forecasts WHERE horizon='1m' AND scored_ts IS NOT NULL AND target_t < ?",
                        (now - MINUTE_KEEP,))

    async def resolve_related(self, now: float) -> None:
        """Once a day: which related markets the broker has (from its own list). A change resubscribes the stream
        and loads their history at once."""
        st = markets.saved(self.db)
        stream = self.provider if self.provider_name == "capital" else None
        if stream is None or not stream.tokens or now - st.get("ts", 0) < markets.RESOLVE_EVERY:
            return
        from .providers.capital import BASES
        try:
            epics = await markets.resolve(BASES[stream.env or "real"], stream.tokens)
        except Exception as e:
            log.warning("related markets: %s", e)
            self.db.put("related:epics", json.dumps({**st, "ts": now - markets.RESOLVE_EVERY + 3600,
                                                     "error": str(e)[:200]}))
            return
        self.db.put("related:epics", json.dumps({"ts": now, "epics": epics}))
        if epics != st.get("epics"):
            self.reset_provider()
            self.history_state["ts"] = 0

    _rules_busy = False

    async def _rules_job(self) -> None:
        self._rules_busy = True
        self._rep("ta", "working", note="qaydalar yoxlanır")
        try:
            res = await asyncio.to_thread(rules.run, self.db)
            heartbeat.beat("rule-blocks", "ok", f"{res['added']} yeni siqnal")
            self._rep("ta", "done", note=f"qaydalar: {res['added']} yeni siqnal"
                                            + (" (tarixçə sınağı)" if res["replay"] else ""))
        except Exception as e:
            log.warning("rules: %s", e)
            heartbeat.beat("rule-blocks", "fail", type(e).__name__)
        finally:
            self._rules_busy = False

    def _rep(self, task: str, status: str, *a, **k) -> None:
        if self.activity is not None:
            self.activity.report(task, status, *a, **k)

    async def step(self) -> None:
        now = time.time()
        await self.poll_once(now)
        live = sum(self.status(s, now) in ("LIVE", "DEMO") for s in candles.METALS)
        self._rep("prices", "done" if live else "error", note=f"{live}/4 metal canlı")
        try:
            n = self.issue_due(now)
            if n:
                self._rep("forecast", "done", note=f"{n} proqnoz verildi")
        except Exception as e:           # issuing failing must not stop scoring (audit 2026-11-24)
            log.exception("issue_due failed")
            self._rep("forecast", "error", note=f"{type(e).__name__}: {str(e)[:100]}")
        try:
            scored = judge.score_due(self.db, now)
            heartbeat.beat("judge-scoring", "ok", f"{scored} proqnoz yoxlandı")
            if scored:
                self._rep("judge", "done", note=f"{scored} proqnoz yoxlandı")
        except Exception as e:
            log.exception("score_due failed")
            heartbeat.beat("judge-scoring", "fail", type(e).__name__)
            self._rep("judge", "error", note=f"{type(e).__name__}: {str(e)[:100]}")

    def refresh_decisions(self) -> None:
        """Off the event loop (a thread), every minute: the liquidity view, the risk gate and the decision per metal."""
        from . import nerve, risk
        now = time.time()
        st = nerve.update(self.db, now)
        self._rep("signals", "done", note=f"{st['state']}: {st['why']}")
        out = {s: risk.decision(self.db, self, s, now) for s in candles.METALS}
        self.decisions = out
        try:                                      # kağız ticarət: only AL / SAT, which already need proof + approval
            from . import paper
            paper.step(self.db, self, out, now)
        except Exception as e:  # noqa: BLE001 — a paper error must never stop the decisions
            log.warning("paper step: %s", e)
        thin = [s for s in out if (out[s]["gate"]["liquidity"] or {}).get("state") == "nazik"]
        closed = [s for s in out if not out[s]["gate"]["open"]]
        calls = [f"{s} {d['name']} {d['call']}" for s in out for d in out[s]["desks"] if d["call"] != "GÖZLƏ"]
        self._rep("liquidity", "done", note=("nazik: " + ", ".join(thin)) if thin else "4 metalda normal")
        self._rep("risk", "done", note=("bağlı: " + ", ".join(f"{s} ({out[s]['gate']['reasons'][0]})" for s in closed))
                  if closed else "4 metalda açıq")
        self._rep("decision", "done", note=", ".join(calls) if calls else "hamısı GÖZLƏ: sübut yoxdur")
        from . import cards
        cards.score(self.db, now)          # Block 16: what really happened, added to the frozen forecast cards

    def nightly_backup(self) -> None:
        """Block 14, in a thread: the database copied, compressed and sent to Cloudflare R2 (if the R2 key is saved)."""
        from . import backup
        creds = self.keys.get("r2")
        if not creds:
            self.db.put("backup:last", json.dumps({"ts": time.time(), "ok": False, "msg": "R2 açarı saxlanmayıb"}))
            return
        if self.db.path == ":memory:":
            return
        import os
        try:
            creds = backup.normalize(creds)
            if not creds.get("bucket"):
                import asyncio
                bucket, how = asyncio.run(backup.resolve(creds))
                if not bucket:
                    raise RuntimeError(how)
                creds = {**creds, "bucket": bucket}
            gz = backup.make_copy(self.db.path, os.path.join(os.path.dirname(self.db.path), "backup"))
            size = os.path.getsize(gz)
            name = backup.upload(creds, gz)
            os.remove(gz)
            msg = {"ts": time.time(), "ok": True, "msg": f"{name} ({size / 1e6:.0f} MB)"}
        except Exception as e:
            msg = {"ts": time.time(), "ok": False, "msg": f"{type(e).__name__}: {str(e)[:200]}"}
        self.db.put("backup:last", json.dumps(msg))
        heartbeat.beat("backup-nightly", "ok" if msg["ok"] else "fail", msg["msg"])
        self._rep("history", "done" if msg["ok"] else "error", note="ehtiyat nüsxə: " + msg["msg"])

    async def _jobs_loop(self) -> None:
        """The brains in their own loop: an alarm must not wait behind a history reload (minutes after an update)."""
        last_dec = 0.0
        while not self._stop.is_set():
            try:
                await self.jobs.tick()
            except Exception:
                log.exception("brain jobs failed")
            day = time.strftime("%Y-%m-%d", time.gmtime())
            if time.gmtime().tm_hour == BACKUP_HOUR_UTC and self.db.get("backup:day") != day:
                self.db.put("backup:day", day)
                try:
                    await asyncio.to_thread(self.nightly_backup)
                except Exception:
                    log.exception("backup failed")
            if time.time() - last_dec > 60:
                last_dec = time.time()
                try:
                    await asyncio.to_thread(self.refresh_decisions)
                except Exception:
                    log.exception("decision failed")
            try:
                await asyncio.wait_for(self._stop.wait(), JOBS_EVERY)
            except asyncio.TimeoutError:
                pass

    async def run(self) -> None:
        last_prune = 0.0
        if self.jobs is not None and (getattr(self, "_jobs_task", None) is None or self._jobs_task.done()):
            self._jobs_task = asyncio.create_task(self._jobs_loop())   # a restarted engine never runs two of these
        try:
            # Off the event loop: a large one-time clean-up must not keep /healthz from answering after an update.
            await asyncio.to_thread(self.migrate)
        except Exception:
            log.exception("migration failed")
        while not self._stop.is_set():
            self._rep("orch", "working", note="dövr başladı")
            t_start = time.time()
            try:
                await self.step()
                if time.time() - last_prune > 3600:
                    self.prune(time.time())
                    last_prune = time.time()
                await self.resolve_related(time.time())
                # Feeds first: the history replay's macro method needs FRED data already loaded.
                if self.feeds is not None:
                    await self.feeds.tick()
                await self.backfill()
                if time.time() - self._weights_ts > 600:
                    self._weights_ts = time.time()
                    await asyncio.to_thread(self.refresh_weights)
                if time.time() - float(self.db.get("rules:ts") or 0) > 900 and not self._rules_busy:
                    self.db.put("rules:ts", str(time.time()))
                    asyncio.get_running_loop().create_task(self._rules_job())   # never blocks the price step
                if time.time() - float(self.db.get("unified:ts") or 0) > UNIFIED_EVERY:
                    self.db.put("unified:ts", str(time.time()))
                    self._rep("judge", "working", note="vahid proqnoz: öz-özünü sınaq")
                    await asyncio.to_thread(unified.refresh, self.db)
                    heartbeat.beat("unified-forecast", "ok", "vahid proqnoz yeniləndi")
                    self._rep("judge", "done", note="vahid proqnoz yeniləndi")
                self._rep("orch", "done", note=f"dövr {time.time() - t_start:.1f} san")
            except Exception as e:   # the loop must survive one bad poll
                log.exception("engine step failed")
                self._rep("orch", "error", note=f"{type(e).__name__}: {str(e)[:100]}")
            try:
                await asyncio.wait_for(self._stop.wait(), self.poll)
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
        if self.provider:
            await self.provider.aclose()
