"""Twelve Data (twelvedata.com): quotes and OHLC history for XAU/USD, XAG/USD, XPT/USD, XPD/USD.

The free plan (Basic: 800 credits/day, 8/min) serves gold only. Its own plan table (symbol_search?show_plan=true,
read 2026-11-11) puts XAU/USD in Basic and XAG/USD, XPT/USD, XPD/USD in Grow (paid; Venture for a business), so a free
key backfills the gold chart and is refused (HTTP 404) for the other three. Using it as the tick source needs a paid
plan too, because every symbol in a quote request costs one credit.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from .base import HistoryProvider, NotServed, PriceProvider, ProviderError, Quote
from .. import netutil

BASE_URL = "https://api.twelvedata.com"
INTERVALS = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h", "1d": "1day", "1w": "1week"}


def td_symbol(symbol: str) -> str:
    return f"{symbol}/USD"


# Answers that mean "this key is not served this symbol" (not in its plan, unknown symbol): asking again changes
# nothing. Anything else (401 bad key, 429 out of credits, 5xx, a time-out) is a failure that may pass.
REFUSED = ("403", "404")


def _error(code: object, text: str) -> ProviderError:
    return (NotServed if str(code) in REFUSED else ProviderError)(text)


def _check_error(data: object) -> None:
    if isinstance(data, dict) and data.get("status") == "error":
        raise _error(data.get("code"), f"{data.get('code', '')} {data.get('message', 'error')}".strip())


def _parse_dt(raw: str) -> int:
    fmt = "%Y-%m-%d %H:%M:%S" if " " in raw else "%Y-%m-%d"
    return int(datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).timestamp())


def parse_time_series(data: object) -> list[tuple[int, float, float, float, float]]:
    _check_error(data)
    if not isinstance(data, dict) or not isinstance(data.get("values"), list):
        raise ProviderError("unexpected time_series response")
    rows = []
    for v in data["values"]:
        try:
            rows.append((_parse_dt(v["datetime"]), float(v["open"]), float(v["high"]),
                         float(v["low"]), float(v["close"])))
        except (KeyError, TypeError, ValueError):
            continue
    rows.sort()
    return rows


def parse_quotes(symbols: list[str], data: object, recv_ts: float) -> tuple[list[Quote], dict[str, str]]:
    _check_error(data)
    if not isinstance(data, dict):
        raise ProviderError("unexpected quote response")
    # A single-symbol request returns the quote itself, a multi-symbol one maps symbol -> quote.
    by_sym = {td_symbol(symbols[0]): data} if len(symbols) == 1 and "symbol" in data else data
    quotes: list[Quote] = []
    errors: dict[str, str] = {}
    for sym in symbols:
        q = by_sym.get(td_symbol(sym))
        try:
            _check_error(q)
            if not isinstance(q, dict):
                raise ProviderError("missing in response")
            price = float(q["close"])
            ts = q.get("last_quote_at") or q.get("timestamp")
            source_ts = float(ts) if ts else recv_ts
            # No quote time from the source: the receive time stands in and the quote says so (never LIVE, C-149).
            quotes.append(Quote(symbol=sym, price=price, source_ts=min(source_ts, recv_ts), source_ts_missing=not ts))
        except (ProviderError, KeyError, TypeError, ValueError) as e:
            errors[sym] = str(e) or type(e).__name__
    return quotes, errors


class _TwelveDataBase:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        if not api_key:
            raise ProviderError("TWELVEDATA_API_KEY is not set")
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(base_url=BASE_URL, timeout=15.0)

    async def _get(self, path: str, params: dict) -> object:
        try:
            # The key goes in a header, not in the URL (audit C-071): URLs end up in logs and error texts.
            r = await netutil.get(self.client, path, params=params, headers={"Authorization": f"apikey {self.api_key}"})
        except httpx.HTTPError as e:
            raise ProviderError(f"{type(e).__name__}: {str(e).replace(self.api_key, '***')}") from e
        if r.status_code != 200:
            raise _error(r.status_code, f"HTTP {r.status_code}{self._reason(r)}")
        try:
            return r.json()
        except ValueError as e:
            raise ProviderError("invalid JSON") from e

    def _reason(self, r: httpx.Response) -> str:
        """Twelve Data's own words for a refused request (the JSON "message"), so the error says why, not only
        "HTTP 404"; the key never appears in it."""
        try:
            data = r.json()
        except ValueError:
            return ""
        msg = data.get("message") if isinstance(data, dict) else None
        if not isinstance(msg, str) or not msg.strip():
            return ""
        return ": " + " ".join(msg.replace(self.api_key, "***").split())[:200]

    async def aclose(self) -> None:
        await self.client.aclose()


class TwelveDataPrices(_TwelveDataBase, PriceProvider):
    name = "twelvedata"
    delayed = False

    async def fetch(self, symbols: list[str]) -> tuple[list[Quote], dict[str, str]]:
        data = await self._get("/quote", {"symbol": ",".join(td_symbol(s) for s in symbols), "interval": "1min"})
        return parse_quotes(symbols, data, time.time())


class TwelveDataHistory(_TwelveDataBase, HistoryProvider):
    name = "twelvedata"
    request_gap = 8.0  # free plan: 8 requests per minute

    async def candles(self, symbol: str, tf: str, limit: int) -> list[tuple[int, float, float, float, float]]:
        data = await self._get("/time_series", {
            "symbol": td_symbol(symbol), "interval": INTERVALS[tf],
            "outputsize": min(max(limit, 1), 5000), "timezone": "UTC",
        })
        return parse_time_series(data)
