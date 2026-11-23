"""Development-only random-walk prices (adapted from pj-trade-gold). Never a default: the panel labels it DEMO."""
from __future__ import annotations

import math
import random
import time

from ..candles import TF as TF_SECONDS, bucket
from .base import HistoryProvider, PriceProvider, Quote

START = {"XAU": 4180.0, "XAG": 60.3, "XPT": 1680.0, "XPD": 1150.0}
VOL = {"XAU": 0.000076, "XAG": 0.000152, "XPT": 0.000122, "XPD": 0.0002}   # per 5 seconds, log


class DemoPrices(PriceProvider):
    name = "demo"
    delayed = False

    def __init__(self, seed: int = 7):
        self.rng = random.Random(seed)
        self.px = dict(START)

    async def fetch(self, symbols: list[str]) -> tuple[list[Quote], dict[str, str]]:
        now = time.time()
        out = []
        for s in symbols:
            self.px[s] *= math.exp(self.rng.gauss(0, VOL[s]))
            out.append(Quote(symbol=s, price=round(self.px[s], 3), source_ts=now))
        return out, {}


class DemoHistory(HistoryProvider):
    name = "demo"

    def __init__(self, seed: int = 11):
        self.seed = seed

    async def candles(self, symbol: str, tf: str, limit: int) -> list[tuple[int, float, float, float, float]]:
        rng = random.Random(f"{self.seed}-{symbol}-{tf}")
        step = TF_SECONDS[tf]
        end = bucket(time.time(), tf) - step
        vol = VOL[symbol] * math.sqrt(step / 5)
        px = START[symbol]
        rows = []
        for i in range(limit):
            t = end - i * step
            c = px
            o = c * math.exp(-rng.gauss(0, vol))
            h = max(o, c) * (1 + abs(rng.gauss(0, vol / 2)))
            l = min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
            rows.append((t, round(o, 3), round(h, 3), round(l, 3), round(c, 3)))
            px = o
        rows.reverse()
        return rows
