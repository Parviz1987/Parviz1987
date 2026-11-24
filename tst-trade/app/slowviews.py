"""Slow views for the long desks (1 week, 10 days, 1 month): ideas taken from a friend's 31-agent project, rewritten
here as methods the Judge tests like any other (none of them had a measured result there).

- cot     «COT mövqeləri»: big funds (managed money) net position in its 3-year range. Crowded long (>= 80th percentile)
          tends to unwind -> lean down; crowded short (<= 20th) -> lean up. A report (Tuesday's positions) is
          public on Friday 20:30 UTC: only reports public before the forecast are used.
- season  «Mövsümilik»: how the metal moved in the same calendar month in past years, from our own daily candles;
          a lean only when at least 5 years exist and 70 % of them agree.
- jewel   «Zərgərlik təqvimi»: jewellery buying before Diwali (gold, silver) and the Lunar New Year (gold): a weak
          «up» in the 21 days before the festival.
All use only data that existed before the forecast's issue time."""
from __future__ import annotations

import bisect
from datetime import date, datetime, timedelta, timezone

from .db import DB

SLOW_HORIZONS = ("1w", "10d", "1mo")
COT_PUBLIC = 3 * 86400 + 20 * 3600 + 1800        # Tuesday 00:00 UTC -> Friday 20:30 UTC
DIWALI = ["2015-11-11", "2016-10-30", "2017-10-19", "2018-11-07", "2019-10-27", "2020-11-14", "2021-11-04",
          "2022-10-24", "2023-11-12", "2024-11-01", "2025-10-20", "2026-11-08", "2027-10-29", "2028-10-17",
          "2029-11-05", "2030-10-26"]
LUNAR_NY = ["2015-02-19", "2016-02-08", "2017-01-28", "2018-02-16", "2019-02-05", "2020-01-25", "2021-02-12",
            "2022-02-01", "2023-01-22", "2024-02-10", "2025-01-29", "2026-02-17", "2027-02-06", "2028-01-26",
            "2029-02-13", "2030-02-03"]
BEFORE_DAYS = 21


def _ts(d: str) -> float:
    return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


class Lookup:
    def __init__(self, db: DB):
        self.cot: dict[str, tuple[list[float], list[float]]] = {}
        try:
            for r in db.execute("SELECT symbol, d, mm_long, mm_short FROM cot ORDER BY d").fetchall():
                ts, nets = self.cot.setdefault(r["symbol"], ([], []))
                ts.append(_ts(r["d"]) + COT_PUBLIC)
                nets.append((r["mm_long"] or 0) - (r["mm_short"] or 0))
        except Exception:
            pass
        # per metal: every finished calendar month as (time it ended, month, return), from our own daily candles
        self.months: dict[str, list[tuple[float, int, float]]] = {}
        groups: dict[tuple[str, int, int], list[tuple[int, float]]] = {}
        for r in db.execute("SELECT symbol, t, c FROM candles WHERE tf='1d' AND symbol IN ('XAU','XAG','XPT','XPD') "
                            "ORDER BY t").fetchall():
            d = datetime.fromtimestamp(r["t"], timezone.utc)
            groups.setdefault((r["symbol"], d.year, d.month), []).append((r["t"], r["c"]))
        for (sym, y, m), v in groups.items():
            if len(v) >= 15 and v[0][1]:
                end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc).timestamp()
                self.months.setdefault(sym, []).append((end, m, v[-1][1] / v[0][1] - 1))

    def _cot(self, metal: str, t: float) -> tuple[float, str]:
        ts, nets = self.cot.get(metal, ([], []))
        i = bisect.bisect_right(ts, t - 60)
        past = nets[max(0, i - 156):i]
        if len(past) < 104:
            return 0.5, f"COT tarixçəsi azdır ({len(past)} həftə, 104 lazımdır)"
        now = past[-1]
        pct = sum(x < now for x in past) / len(past) * 100
        if pct >= 80:
            return 0.45, f"fondlar çox alıb (3 ilin {pct:.0f}-ci faizi): geri çəkilmə ehtimalı"
        if pct <= 20:
            return 0.55, f"fondlar çox satıb (3 ilin {pct:.0f}-ci faizi): geri alış ehtimalı"
        return 0.5, f"fondların mövqeyi adi aralıqdadır ({pct:.0f}-ci faiz)"

    def _season(self, metal: str, t: float) -> tuple[float, str]:
        month = datetime.fromtimestamp(t, timezone.utc).month
        rets = [r for end, m, r in self.months.get(metal, []) if m == month and end <= t]
        if len(rets) < 5:
            return 0.5, f"bu ay üçün {len(rets)} il var (5 lazımdır)"
        up = sum(r > 0 for r in rets) / len(rets)
        if up >= 0.7:
            return 0.55, f"son {len(rets)} ilin {up * 100:.0f} %-ində bu ay qalxıb"
        if up <= 0.3:
            return 0.45, f"son {len(rets)} ilin {(1 - up) * 100:.0f} %-ində bu ay düşüb"
        return 0.5, f"bu ayın meyli aydın deyil ({up * 100:.0f} % qalxıb, {len(rets)} il)"

    @staticmethod
    def _jewel(metal: str, t: float) -> tuple[float, str]:
        today = datetime.fromtimestamp(t, timezone.utc).date()
        fests = [("Divali", DIWALI, ("XAU", "XAG")), ("Çin Yeni ili", LUNAR_NY, ("XAU",))]
        for name, days, metals in fests:
            if metal not in metals:
                continue
            for d in days:
                f = date.fromisoformat(d)
                if timedelta(0) < f - today <= timedelta(days=BEFORE_DAYS):
                    return 0.55, f"{name}ə {(f - today).days} gün qalır: zərgərlik alışı mövsümü"
        return 0.5, "bayram öncəsi alış mövsümü deyil"

    def views(self, metal: str, t: float, horizon: str) -> dict:
        if horizon not in SLOW_HORIZONS:
            return {}
        return {"cot": self._cot(metal, t), "season": self._season(metal, t), "jewel": self._jewel(metal, t)}
