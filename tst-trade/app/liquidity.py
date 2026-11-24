"""Likvidlik agenti (liquidity): is the market thin right now? Two plain measures per metal, from the live stream:
- spread: the bid/ask gap as a share of the price, sampled once a minute; «wide» when it is more than twice its usual
  (median of the last 24 hours);
- activity: price updates in the last 5 minutes against the usual 5 minutes of the last 24 hours; «quiet» below 25 %.
A thin market makes any forecast cost more to act on (wider spread) and moves erratically: the risk gate reads it.
Kept in memory (it rebuilds within minutes after a restart); nothing is guessed while there are too few samples."""
from __future__ import annotations

import time
from collections import deque

WIDE_X, QUIET_SHARE, MIN_SAMPLES = 2.0, 0.25, 30


class Liquidity:
    def __init__(self):
        self.spreads: dict[str, deque] = {}       # symbol -> (minute, spread share)
        self.ticks: dict[str, deque] = {}         # symbol -> (minute, updates in that minute)

    def add(self, symbol: str, now: float, bid: float | None, ask: float | None) -> None:
        minute = int(now // 60)
        t = self.ticks.setdefault(symbol, deque(maxlen=1440))
        if t and t[-1][0] == minute:
            t[-1] = (minute, t[-1][1] + 1)
        else:
            t.append((minute, 1))
        if bid and ask and ask >= bid:
            s = self.spreads.setdefault(symbol, deque(maxlen=1440))
            if not s or s[-1][0] != minute:
                s.append((minute, (ask - bid) / ((ask + bid) / 2)))

    def view(self, symbol: str, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        minute = int(now // 60)
        out = {"symbol": symbol, "state": "naməlum", "reasons": []}
        s = self.spreads.get(symbol) or deque()
        t = self.ticks.get(symbol) or deque()
        if len(s) < MIN_SAMPLES or len(t) < MIN_SAMPLES:
            out["reasons"].append(f"ölçü azdır ({len(s)} dəqiqə)")
            return out
        usual = sorted(x for _, x in s)[len(s) // 2]
        now_spread = s[-1][1]
        last5 = sum(n for m, n in t if m > minute - 5)
        active = [n for m, n in t if m <= minute - 5]
        usual5 = (sum(active) / max(1, len(active))) * 5
        out.update({"spread_pct": round(now_spread * 100, 4), "usual_spread_pct": round(usual * 100, 4),
                    "updates_5m": last5, "usual_updates_5m": round(usual5)})
        if usual and now_spread > WIDE_X * usual:
            out["reasons"].append(f"spred adətdən {now_spread / usual:.1f} dəfə genişdir")
        if usual5 and last5 < QUIET_SHARE * usual5:
            out["reasons"].append(f"bazar sakitdir: 5 dəqiqədə {last5} yenilənmə (adətən {usual5:.0f})")
        out["state"] = "nazik" if out["reasons"] else "normal"
        return out
