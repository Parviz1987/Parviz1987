from __future__ import annotations

from dataclasses import dataclass

# Internal metal codes -> display names. Prices are always USD per troy ounce.
METALS: dict[str, str] = {"XAU": "Gold", "XAG": "Silver", "XPT": "Platinum", "XPD": "Palladium"}


class ProviderError(Exception):
    pass


class NotServed(ProviderError):
    """The source answered, and refused this symbol for this key (HTTP 403 / 404: not in the plan, unknown symbol).
    Asking again changes nothing until the plan does; a time-out, a rate limit or a 5xx is a plain ProviderError."""


@dataclass(frozen=True)
class Quote:
    symbol: str          # XAU / XAG / XPT / XPD
    price: float         # USD / troy oz
    source_ts: float     # epoch seconds reported by the provider (when the price was set)
    bid: float | None = None
    ask: float | None = None
    # True when the provider sent no usable quote time and recv time stands in for source_ts (agent #19 says so).
    source_ts_missing: bool = False


class PriceProvider:
    """Polled spot-price source."""

    name = "base"
    # True when the provider's terms say data is delayed: the UI then never shows LIVE.
    delayed = False

    async def fetch(self, symbols: list[str]) -> tuple[list[Quote], dict[str, str]]:
        """Return quotes that succeeded and per-symbol error messages for those that failed."""
        raise NotImplementedError

    async def aclose(self) -> None:
        pass


class HistoryProvider:
    """Source of historical OHLC used to backfill the chart."""

    name = "base"
    # Seconds between requests during backfill (free plans are rate limited per minute).
    request_gap: float = 0.0

    async def candles(self, symbol: str, tf: str, limit: int) -> list[tuple[int, float, float, float, float]]:
        raise NotImplementedError

    async def aclose(self) -> None:
        pass
