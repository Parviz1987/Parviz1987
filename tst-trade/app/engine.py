"""The running heart of TST Trade: polls prices, builds candles, issues forecasts at every candle close, has the
Judge score them, and backfills history (Twelve Data key) for the longer horizons."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from . import candles, forecast, judge, surprise
from .db import DB
from .keys import KeyStore
from .providers.base import NotServed, ProviderError, Quote
from .providers.capital import CapitalHistory, CapitalStream
from .providers.demo import DemoHistory, DemoPrices
from .providers.goldapi import GoldApiProvider
from .providers.twelvedata import TwelveDataHistory, TwelveDataPrices

log = logging.getLogger("tst.engine")
HISTORY_EVERY = 6 * 3600
HISTORY_LIMIT = {"1m": 1500, "1h": 1500, "4h": 1500, "1d": 2000, "1w": 600}
BACKTEST_MAX = 2000
TICK_KEEP = 3 * 86400
MINUTE_KEEP = 30 * 86400


def market_open(ts: float) -> bool:
    """Spot metals trade almost 24/5. Approximate weekly close: Friday 21:00 to Sunday 22:00 UTC."""
    d = datetime.fromtimestamp(ts, timezone.utc)
    wd, h = d.weekday(), d.hour
    if wd == 5:
        return False
    if wd == 4 and h >= 21:
        return False
    if wd == 6 and h < 22:
        return False
    return True


target_time = forecast.target_time   # kept here for older imports


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
            self.series[sid] = ([r["d"] for r in rows], [r["v"] for r in rows])

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
        self.history_state: dict = json.loads(db.get("history_state") or "{}")
        self._macro_cache = None
        self._rel_cache = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ---------- price source ----------
    def chosen_provider(self) -> str:
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
            return CapitalStream(creds, on_quote=self.on_quote), "capital"
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
        """A streamed price: stored the moment it arrives (no wait for the next poll)."""
        now = time.time()
        self.quotes[q.symbol] = {"price": q.price, "source_ts": q.source_ts, "recv_ts": now,
                                 "ts_missing": q.source_ts_missing}
        self.db.execute("INSERT INTO ticks(symbol, ts, price, source, source_ts) VALUES(?,?,?,?,?)",
                        (q.symbol, now, q.price, "capital", q.source_ts))
        candles.add_tick(self.db, q.symbol, now, q.price)
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
            self.db.execute("INSERT INTO ticks(symbol, ts, price, source, source_ts) VALUES(?,?,?,?,?)",
                            (q.symbol, now, q.price, self.provider_name, q.source_ts))
            candles.add_tick(self.db, q.symbol, now, q.price)
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
        sig = ",".join(forecast.METHODS)
        if self.db.get("methods_sig") != sig:
            # A new forecast method: the history is replayed now for it (old forecasts stay as issued).
            self.history_state["ts"] = 0
            self.db.put("methods_sig", sig)
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
                fc = forecast.build(past, h, macro.at(issued_t) if tf == "1d" else None, issued_t,
                                    rel.window(issued_t, h))
                if fc is None:
                    continue
                n += judge.issue(self.db, sym, h, issued_t, target_time(issued_t, h), fc, mode)
        return n

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
                out.append((CapitalHistory(self.keys.get("capital"), stream), True))
            else:
                out.append((TwelveDataHistory(self.keys.first("twelvedata")), False))
        return out

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
        for src, replace in sources:
            try:
                for sym in candles.METALS:
                    for tf, limit in HISTORY_LIMIT.items():
                        line = result.setdefault(sym, {})
                        try:
                            rows = await src.candles(sym, tf, limit)
                            candles.store_history(self.db, sym, tf, rows, replace=replace)
                            line[tf] = (line.get(tf, "") + f" {src.name}: {len(rows)} şam").strip()
                        except NotServed as e:
                            line[tf] = (line.get(tf, "") + f" {src.name}: planda yoxdur ({str(e)[:60]})").strip()
                            if src.name == "twelvedata":
                                break
                        except ProviderError as e:
                            line[tf] = (line.get(tf, "") + f" {src.name}: xəta ({str(e)[:80]})").strip()
                        if src.request_gap:
                            await asyncio.sleep(src.request_gap)
            except Exception as e:   # one source failing (login refused...) must not stop the next one
                log.warning("history %s: %s", src.name, e)
                result.setdefault("*", {})[src.name] = f"xəta: {str(e)[:120]}"
            finally:
                await src.aclose()
        self.history_state = {"ts": now, "result": result, "source": ", ".join(s.name for s, _ in sources)}
        self.db.put("history_state", json.dumps(self.history_state))
        # The walk-forward replay is CPU work: off the event loop, so prices keep coming in meanwhile.
        await asyncio.to_thread(self.backtest, now)
        return self.history_state

    def backtest(self, now: float | None = None) -> int:
        """Walk forward over stored candles: each forecast sees only the candles before it (mode 'history')."""
        now = time.time() if now is None else now
        n = 0
        macro = MacroLookup(self.db)
        rel = surprise.Lookup(self.db)
        first = macro.first_day()
        if first:
            # Replayed before FRED data arrived: those macro forecasts said "no data". Now that the data covers
            # their dates, they are replayed (only these rows; every other forecast stays as issued).
            start = int(datetime.strptime(first, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) + 14 * 86400
            self.db.execute("DELETE FROM forecasts WHERE mode='history' AND method='macro' AND basis=? AND issued_t>?",
                            ("FRED məlumatı yoxdur", start))
        for h, tf in forecast.HORIZONS.items():
            step = candles.TF[tf]
            for sym in candles.METALS:
                rows = candles.closed(self.db, sym, tf, now, limit=BACKTEST_MAX + forecast.MIN_CANDLES)
                k = forecast.steps_of(h)
                batch: list = []
                done = {r["issued_t"] for r in self.db.execute(
                    "SELECT issued_t FROM forecasts WHERE symbol=? AND horizon=? AND mode='history' "
                    "GROUP BY issued_t HAVING COUNT(*) >= ?", (sym, h, len(forecast.methods_for(h)))).fetchall()}
                for i in range(forecast.MIN_CANDLES, len(rows)):
                    t = rows[i]["t"]
                    if t in done:
                        continue   # replayed before: forecasts never change once issued
                    if rows[i]["t"] - rows[i - 1]["t"] > 3 * step and tf not in ("1d", "1w"):
                        continue   # a gap (weekend): the candle after it is not "the next one"
                    fc = forecast.build(rows[max(0, i - forecast.history_need(h)):i], h,
                                        macro.at(t) if tf == "1d" else None, t, rel.window(t, h))
                    if fc is None:
                        continue
                    target = rows[i + k - 1]["t"] + step if i + k - 1 < len(rows) else target_time(t, h)
                    batch += judge.issue_rows(sym, h, t, target, fc, "history")
                # one transaction per metal and horizon (thousands of small commits are slow on a small disk)
                judge.insert(self.db, batch)
                n += len(batch)
        judge.score_due(self.db, now)
        return n

    # ---------- loop ----------
    def prune(self, now: float) -> None:
        """Ticks live 3 days; one-minute candles and their scored forecasts 30 days (the Judge's one-minute verdict
        covers the last month, which is also the most relevant one). Everything longer is kept."""
        self.db.execute("DELETE FROM ticks WHERE ts < ?", (now - TICK_KEEP,))
        self.db.execute("DELETE FROM candles WHERE tf IN ('1m', '5m') AND t < ?", (now - MINUTE_KEEP,))
        self.db.execute("DELETE FROM forecasts WHERE horizon='1m' AND scored_ts IS NOT NULL AND target_t < ?",
                        (now - MINUTE_KEEP,))

    async def step(self) -> None:
        now = time.time()
        await self.poll_once(now)
        self.issue_due(now)
        judge.score_due(self.db, now)

    async def run(self) -> None:
        last_prune = 0.0
        try:
            # Off the event loop: a large one-time clean-up must not keep /healthz from answering after an update.
            await asyncio.to_thread(self.migrate)
        except Exception:
            log.exception("migration failed")
        while not self._stop.is_set():
            try:
                await self.step()
                if time.time() - last_prune > 3600:
                    self.prune(time.time())
                    last_prune = time.time()
                # Feeds first: the history replay's macro method needs FRED data already loaded.
                if self.feeds is not None:
                    await self.feeds.tick()
                await self.backfill()
                if self.jobs is not None:
                    await self.jobs.tick()
            except Exception:   # the loop must survive one bad poll
                log.exception("engine step failed")
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
