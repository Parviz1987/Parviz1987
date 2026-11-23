"""The running heart of TST Trade: polls prices, builds candles, issues forecasts at every candle close, has the
Judge score them, and backfills history (Twelve Data key) for the longer horizons."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from . import candles, forecast, judge
from .db import DB
from .keys import KeyStore
from .providers.base import NotServed, ProviderError, Quote
from .providers.capital import CapitalStream
from .providers.demo import DemoHistory, DemoPrices
from .providers.goldapi import GoldApiProvider
from .providers.twelvedata import TwelveDataHistory, TwelveDataPrices

log = logging.getLogger("tst.engine")
HISTORY_EVERY = 6 * 3600
HISTORY_LIMIT = {"1m": 1500, "1h": 1500, "1d": 2000, "1w": 600}
BACKTEST_MAX = 2000
TICK_KEEP = 3 * 86400


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

    # ---------- forecasts ----------
    def issue_due(self, now: float | None = None, mode: str = "live") -> int:
        """At each candle close: one forecast per horizon, metal and method, for the next candle."""
        now = time.time() if now is None else now
        n = 0
        for h, tf in forecast.HORIZONS.items():
            issued_t = candles.bucket(now, tf)
            step = candles.TF[tf]
            for sym in candles.METALS:
                past = candles.closed(self.db, sym, tf, now, limit=200)
                # Only right after a real candle: a closed market or a feed gap issues nothing.
                if not past or past[-1]["t"] != issued_t - step:
                    continue
                fc = forecast.build([c["c"] for c in past], h)
                if fc is None:
                    continue
                n += judge.issue(self.db, sym, h, issued_t, issued_t + step, fc, mode)
        return n

    # ---------- history and backtest ----------
    async def backfill(self, force: bool = False) -> dict:
        key = self.keys.first("twelvedata")
        now = time.time()
        if not force and now - self.history_state.get("ts", 0) < HISTORY_EVERY:
            return self.history_state
        if self.chosen_provider() == "demo":
            src = DemoHistory()
        elif key:
            src = TwelveDataHistory(key)
        else:
            self.history_state = {"ts": now, "result": {}, "note": "Twelve Data açarı yoxdur: tarixçə yüklənmir"}
            self.db.put("history_state", json.dumps(self.history_state))
            return self.history_state
        result: dict[str, dict[str, str]] = {}
        try:
            for sym in candles.METALS:
                result[sym] = {}
                for tf, limit in HISTORY_LIMIT.items():
                    try:
                        rows = await src.candles(sym, tf, limit)
                        candles.store_history(self.db, sym, tf, rows)
                        result[sym][tf] = f"{len(rows)} şam"
                    except NotServed as e:
                        result[sym][tf] = f"planda yoxdur: {e}"
                        break
                    except ProviderError as e:
                        result[sym][tf] = f"xəta: {e}"
                    if src.request_gap:
                        await asyncio.sleep(src.request_gap)
        finally:
            await src.aclose()
        self.history_state = {"ts": now, "result": result, "source": src.name}
        self.db.put("history_state", json.dumps(self.history_state))
        # The walk-forward replay is CPU work: off the event loop, so prices keep coming in meanwhile.
        await asyncio.to_thread(self.backtest, now)
        return self.history_state

    def backtest(self, now: float | None = None) -> int:
        """Walk forward over stored candles: each forecast sees only the candles before it (mode 'history')."""
        now = time.time() if now is None else now
        n = 0
        for h, tf in forecast.HORIZONS.items():
            step = candles.TF[tf]
            for sym in candles.METALS:
                rows = candles.closed(self.db, sym, tf, now, limit=BACKTEST_MAX + forecast.MIN_CANDLES)
                closes = [c["c"] for c in rows]
                for i in range(forecast.MIN_CANDLES, len(rows)):
                    if rows[i]["t"] - rows[i - 1]["t"] > 3 * step and tf not in ("1d", "1w"):
                        continue   # a gap (weekend): the candle after it is not "the next one"
                    fc = forecast.build(closes[max(0, i - 200):i], h)
                    if fc is None:
                        continue
                    t = rows[i]["t"]
                    n += judge.issue(self.db, sym, h, t, t + step, fc, "history")
        judge.score_due(self.db, now)
        return n

    # ---------- loop ----------
    def prune(self, now: float) -> None:
        self.db.execute("DELETE FROM ticks WHERE ts < ?", (now - TICK_KEEP,))

    async def step(self) -> None:
        now = time.time()
        await self.poll_once(now)
        self.issue_due(now)
        judge.score_due(self.db, now)

    async def run(self) -> None:
        last_prune = 0.0
        while not self._stop.is_set():
            try:
                await self.step()
                if time.time() - last_prune > 3600:
                    self.prune(time.time())
                    last_prune = time.time()
                await self.backfill()
                if self.feeds is not None:
                    await self.feeds.tick()
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
