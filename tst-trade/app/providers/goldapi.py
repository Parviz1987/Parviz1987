"""gold-api.com: free spot prices for XAU/XAG/XPT/XPD, no API key.

Used as the default tick source so the board works on day one. Its free plan has no intraday history (/history by
hour or minute is Premium; /history and /ohlc share 10 requests an hour), so candles are built locally from ticks
(or backfilled from Twelve Data for the metals a configured key serves).

How it is asked (its docs and FAQ, read on the live site 2026-11-11):
- A price is set every 30 s, and each /price answer names the seconds left until the next one in cache-control
  ("cache each response for 30 seconds"; "IPs that spam the API may be banned"). While an answer stands, a poll gets
  it from memory: every metal is requested once per price, however short PRICE_POLL_SECONDS is.
- One connection is kept between polls. httpx drops an idle one after 5 s, so every 15 s poll used to pay for a new
  DNS lookup, TCP and TLS set-up; some of those take 5 s and more (measured from a clean address), and one over the
  8 s limit is the feed's "ConnectTimeout".
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Callable

import httpx

from .base import PriceProvider, ProviderError, Quote
from .. import netutil

BASE_URL = "https://api.gold-api.com"
# The real-time endpoint has no published rate limit, but the terms ban "multiple requests per second" from one IP
# (gold-api.com/terms, checked 2026-10-09). There is no multi-symbol endpoint, so the metals are asked one by one.
REQUEST_GAP = 1.1
# The longest an answer stands, whatever its cache-control says (the source's own period): a wrong header must not
# freeze the board's price.
CACHE_MAX = 30.0
# Idle seconds a connection is kept: longer than one price period (the next request reuses it), shorter than the
# once-a-minute poll of a closed market. The server drops an idle connection itself after 26-29 s (measured from a
# clean address 2026-11-11: reused after 26 s idle, a new one after 29 s): one it has closed is noticed before it
# is used and replaced, one it closes as the request goes out is a NO_ANSWER failure and is asked again (below).
KEEPALIVE_SECONDS = 45.0
# Setting a connection up takes about 0.1 s. Over this limit the attempt is dropped and made once more (below).
CONNECT_TIMEOUT = 4.0
# Failures in which the source answered nothing: the connection was not set up, or a kept one was closed by the
# server as it was used. The request is sent once more, once a poll (a source that is down must not double the
# length of a poll). A slow answer (ReadTimeout) or an error status is not asked twice.
NO_ANSWER = (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError)


def cache_seconds(cache_control: str | None, age: str | None = None) -> float:
    """Seconds an answer still stands by its Cache-Control (max-age less Age), at most CACHE_MAX; 0 = ask again."""
    directives = [d.strip().lower() for d in (cache_control or "").split(",")]
    if "no-store" in directives or "no-cache" in directives:
        return 0.0
    for d in directives:
        if d.startswith("max-age="):
            try:
                left = float(d[8:]) - (float(age) if age else 0.0)
            except ValueError:
                return 0.0
            return min(max(left, 0.0), CACHE_MAX)
    return 0.0


def parse_ts(raw: object, fallback: float | None) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw) / (1000.0 if raw > 1e12 else 1.0)
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return fallback


def parse_quote(symbol: str, data: object, recv_ts: float) -> Quote:
    if not isinstance(data, dict):
        raise ProviderError("unexpected response")
    price = data.get("price")
    if isinstance(price, str):  # tolerate a numeric string, e.g. "4180.25"
        try:
            price = float(price.replace(",", ""))
        except ValueError:
            pass
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
        raise ProviderError(f"no price in response: {str(data)[:120]}")
    got = str(data.get("symbol") or symbol).upper()
    if got != symbol:
        raise ProviderError(f"symbol mismatch: asked {symbol}, got {got}")
    # No usable updatedAt: the receive time stands in, but the quote says so instead of looking fresh for sure
    # (a stuck answer with no time would otherwise pass as LIVE; agent #19 reports the flag).
    ts = parse_ts(data.get("updatedAt"), None)
    return Quote(symbol=symbol, price=float(price), source_ts=recv_ts if ts is None else ts,
                 source_ts_missing=ts is None)


class GoldApiProvider(PriceProvider):
    name = "gold-api.com"
    delayed = False

    def __init__(self, client: httpx.AsyncClient | None = None, request_gap: float = REQUEST_GAP,
                 clock: Callable[[], float] = time.monotonic):
        self.request_gap = request_gap
        self.clock = clock
        self.client = client or httpx.AsyncClient(
            base_url=BASE_URL, timeout=httpx.Timeout(8.0, connect=CONNECT_TIMEOUT), headers={"User-Agent": "tst-trade/1.0"},
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2, keepalive_expiry=KEEPALIVE_SECONDS))
        self._standing: dict[str, tuple[Quote, float]] = {}    # metal -> (answer, clock time it stands until)
        self._last_request: float | None = None                # clock time the last request ended
        self._retry = True                                     # this poll's one retry is still unused

    async def _get(self, symbol: str) -> httpx.Response:
        """One request, never within request_gap of the one before; once a poll, a NO_ANSWER failure is retried."""
        while True:
            if self._last_request is not None:
                wait = self._last_request + self.request_gap - self.clock()
                if wait > 0:
                    await asyncio.sleep(wait)
            try:
                return await netutil.get(self.client, f"/price/{symbol}")
            except NO_ANSWER:
                if not self._retry:
                    raise
                self._retry = False
            finally:
                self._last_request = self.clock()

    async def _one(self, symbol: str) -> Quote:
        try:
            r = await self._get(symbol)
        except httpx.HTTPError as e:
            raise ProviderError(f"{type(e).__name__}: {e}") from e
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError as e:
            raise ProviderError("invalid JSON") from e
        quote = parse_quote(symbol, data, time.time())
        left = cache_seconds(r.headers.get("cache-control"), r.headers.get("age"))
        if left > 0:
            self._standing[symbol] = (quote, self.clock() + left)
        return quote

    async def fetch(self, symbols: list[str]) -> tuple[list[Quote], dict[str, str]]:
        quotes: list[Quote] = []
        errors: dict[str, str] = {}
        self._retry = True
        for sym in symbols:
            standing = self._standing.get(sym)
            if standing is not None and self.clock() < standing[1]:
                quotes.append(standing[0])      # the source has not set a new price yet: the same answer, no request
                continue
            # Past its time an answer is dropped before the request: a failed request is an error, never an old price.
            self._standing.pop(sym, None)
            try:
                quotes.append(await self._one(sym))
            except Exception as e:  # one metal failing must not cost the others their price
                errors[sym] = str(e) or type(e).__name__
        return quotes, errors

    async def aclose(self) -> None:
        await self.client.aclose()
