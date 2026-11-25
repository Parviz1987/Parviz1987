"""Fundamental blok (owner 2026-11-25: «every block as complete as the technical one»).

The drivers professionals use for gold (World Gold Council GRAM: opportunity cost, risk, economic expansion, central-bank
demand; dollar; Fed path; positioning; data surprises), each as a rule of the Bilik kitabı that our code detects on
every trading day and the Judge measures on its own (next daily candle and stop + target, like the technical rules).

Timing: a daily candle labelled D is decided at its close; only values PUBLISHED by then are used (FRED daily series
come out the next afternoon: lag 2 days; the broad dollar index weekly: lag 10 days; COT on Friday for the Tuesday).
Stored in rule_signals (tf «1d», ids FA-*), so the records, the stop + target test and the walk-forward weights are
the same machinery as the technical block. The block reaches the forecasts as one voice, «fundamental»."""
from __future__ import annotations

import bisect
import time
from datetime import datetime, timezone

from .db import DB

LAG_DAYS = {"DFII10": 2, "DGS2": 2, "T10YIE": 2, "DTWEXBGS": 10}
COT_PUBLIC = 3 * 86400 + 20 * 3600 + 1800        # Tuesday 00:00 UTC -> Friday 20:30 UTC
FA_VER = "2026-11-25.2"
FAMILY = {"FA-RY-1": "faiz", "FA-RY-2": "faiz", "FA-FED-1": "faiz", "FA-BE-1": "faiz", "FA-USD-1": "dollar",
          "FA-COT-1": "mövqe", "FA-COT-2": "mövqe", "FA-SURP-1": "sürpriz", "FA-CB-1": "mərkəzi bank"}
OZ_PER_TONNE = 32150.7466
CB_PUBLIC_DAYS = 45      # a month's IMF figure is public about six weeks after the month ends (counted cautiously)


class Data:
    """Every input as it was known at a moment (no revisions from the future: ALFRED first values where kept)."""

    def __init__(self, db: DB):
        self.series: dict[str, tuple[list[str], list[float]]] = {}
        for sid in LAG_DAYS:
            try:
                rows = db.execute("SELECT d, v FROM macro WHERE series=? ORDER BY d", (sid,)).fetchall()
                first = {r["d"]: r["v"] for r in db.execute("SELECT d, v FROM macro_first WHERE series=?",
                                                            (sid,)).fetchall()}
            except Exception:
                rows, first = [], {}
            self.series[sid] = ([r["d"] for r in rows], [first.get(r["d"], r["v"]) for r in rows])
        self.cot: dict[str, tuple[list[float], list[float]]] = {}
        try:
            for r in db.execute("SELECT symbol, d, mm_long, mm_short FROM cot ORDER BY d").fetchall():
                t = datetime.fromisoformat(r["d"]).replace(tzinfo=timezone.utc).timestamp() + COT_PUBLIC
                ts, nets = self.cot.setdefault(r["symbol"], ([], []))
                ts.append(t)
                nets.append((r["mm_long"] or 0) - (r["mm_short"] or 0))
        except Exception:
            pass
        from . import surprise
        self.sur = surprise.Lookup(db)
        # central banks' net purchases per month (tonnes), with the moment each month became public
        self.cb_t: list[float] = []
        self.cb_net: list[float] = []
        try:
            by: dict[str, dict[str, float]] = {}
            for r in db.execute("SELECT country, period, oz FROM cb_gold").fetchall():
                by.setdefault(r["period"], {})[r["country"]] = r["oz"]
            months = sorted(by)
            for a, b in zip(months, months[1:]):
                both = set(by[a]) & set(by[b])           # only countries reported in both months
                if len(both) < 5:
                    continue
                net = sum(by[b][c] - by[a][c] for c in both) / OZ_PER_TONNE
                y, m = int(b[:4]), int(b[5:7])
                end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc).timestamp()
                self.cb_t.append(end + CB_PUBLIC_DAYS * 86400)
                self.cb_net.append(net)
        except Exception:
            pass

    def change(self, sid: str, t: float, days: int, pct: bool = False) -> float | None:
        """The change over `days` observations of the last value published before t."""
        ds, vs = self.series.get(sid, ([], []))
        day = datetime.fromtimestamp(t - (LAG_DAYS[sid] - 1) * 86400, timezone.utc).strftime("%Y-%m-%d")
        i = bisect.bisect_left(ds, day) - 1
        if i < days:
            return None
        a, b = vs[i - days], vs[i]
        return (b / a - 1) * 100 if pct else b - a

    def cot_at(self, metal: str, t: float) -> list[float]:
        ts, nets = self.cot.get(metal, ([], []))
        i = bisect.bisect_right(ts, t)
        return nets[max(0, i - 156):i]

    def surprise_sum(self, t: float, days: int = 14) -> tuple[float, int]:
        lo = bisect.bisect_left(self.sur.ts, t - days * 86400)
        hi = bisect.bisect_right(self.sur.ts, t)
        items = self.sur.items[lo:hi]
        return sum(s["gold"] * s["weight"] for s in items), len(items)


def detect(data: Data, metal: str, t: float) -> list[tuple[str, int, str]]:
    """The fundamental rules at moment t (what was published by then)."""
    out = []
    r5 = data.change("DFII10", t, 5)
    if r5 is not None and abs(r5) >= 0.10:
        out.append(("FA-RY-1", 1 if r5 < 0 else -1, f"real faiz 5 günə {r5:+.2f} pp"))
    r20 = data.change("DFII10", t, 20)
    if r20 is not None and abs(r20) >= 0.25:
        out.append(("FA-RY-2", 1 if r20 < 0 else -1, f"real faiz 20 günə {r20:+.2f} pp (trend)"))
    y2 = data.change("DGS2", t, 5)
    if y2 is not None and abs(y2) >= 0.15:
        out.append(("FA-FED-1", 1 if y2 < 0 else -1, f"2 illik faiz 5 günə {y2:+.2f} pp: bazar Fed-dən "
                                                      f"{'daha çox endirim' if y2 < 0 else 'daha az endirim'} gözləyir"))
    be = data.change("T10YIE", t, 5)
    if be is not None and abs(be) >= 0.08:
        out.append(("FA-BE-1", 1 if be > 0 else -1, f"inflyasiya gözləntisi 5 günə {be:+.2f} pp"))
    usd = data.change("DTWEXBGS", t, 5, pct=True)
    if usd is not None and abs(usd) >= 1.0:
        out.append(("FA-USD-1", 1 if usd < 0 else -1, f"geniş dollar indeksi 5 günə {usd:+.2f} %"))
    past = data.cot_at(metal, t)
    if len(past) >= 104:
        now = past[-1]
        pct = sum(x < now for x in past) / len(past) * 100
        if pct >= 80:
            out.append(("FA-COT-1", -1, f"fondlar çox alıb (3 ilin {pct:.0f}-ci faizi)"))
        elif pct <= 20:
            out.append(("FA-COT-1", 1, f"fondlar çox satıb (3 ilin {pct:.0f}-ci faizi)"))
        d = [b - a for a, b in zip(past[-4:], past[-3:])]
        moves = sorted(abs(b - a) for a, b in zip(past, past[1:]))
        big = moves[int(len(moves) * 0.6)] if moves else 0
        if len(d) == 3 and (all(x > 0 for x in d) or all(x < 0 for x in d)) and abs(sum(d)) >= 3 * big:
            out.append(("FA-COT-2", 1 if d[0] > 0 else -1, "fondlar 3 həftədir ardıcıl " +
                        ("alır" if d[0] > 0 else "satır")))
    i = bisect.bisect_right(data.cb_t, t)
    nets = data.cb_net[:i]
    if len(nets) >= 27:
        sums = [sum(nets[k - 3:k]) for k in range(3, len(nets) + 1)][-36:]
        now3 = sums[-1]
        pct = sum(x < now3 for x in sums) / len(sums) * 100
        if pct >= 80:
            out.append(("FA-CB-1", 1, f"mərkəzi banklar son 3 ayda {now3:+.0f} ton aldı: 3 ilin ən güclü alışları "
                                      f"({pct:.0f}-ci faiz)"))
        elif pct <= 20:
            out.append(("FA-CB-1", -1, f"mərkəzi banklar son 3 ayda {now3:+.0f} ton: 3 ilin ən zəif alışları "
                                       f"({pct:.0f}-ci faiz)"))
    s, n = data.surprise_sum(t)
    if n >= 3 and abs(s) >= 2:
        out.append(("FA-SURP-1", 1 if s > 0 else -1, f"son 14 gündə {n} ABŞ rəqəmi: sürprizlər qızıl üçün "
                                                     f"{'müsbət' if s > 0 else 'mənfi'} ({s:+.1f})"))
    return out


def run(db: DB, now: float | None = None) -> int:
    """Detect on every daily candle (history once, then the newest); next candle and stop + target as for TA rules."""
    from . import candles, rules
    from .candles import METALS
    rules.ensure(db)
    now = time.time() if now is None else now
    data = Data(db)
    added = 0
    for sym in METALS:
        cs = [dict(r) for r in candles.closed(db, sym, "1d", now, limit=4500)]
        if len(cs) < 30:
            continue
        ind = rules.Ind(cs)
        # replayed again once the central-bank data first arrives (the IMF feed runs once a day)
        mark = f"fa:ver:{FA_VER}:{'cb' if data.cb_net else 'nocb'}:{sym}"
        done = int(db.get(mark) or 0)
        rows = []
        for i in range(20, len(cs)):
            t = cs[i]["t"]
            if t <= done:
                continue
            known = t + 86400 - 7200            # the candle's close (22:00 UTC): what was published by then
            p1 = cs[i + 1]["c"] if i + 1 < len(cs) else None
            for rule, d, note in detect(data, sym, known):
                rows.append((sym, "1d", t, rule, d, cs[i]["c"], p1, "history" if not done else "live", note[:120],
                             ind.atr[i], ind.adx[i]))
        db.executemany("INSERT OR IGNORE INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note, atr, adx) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
        added += len(rows)
        idx = {x["t"]: k for k, x in enumerate(cs)}
        upd = []
        for r in db.execute("SELECT t, rule, dir, price1 FROM rule_signals WHERE metal=? AND tf='1d' AND rule LIKE 'FA-%' "
                            "AND (price1 IS NULL OR rr IS NULL)", (sym,)).fetchall():
            k = idx.get(r["t"])
            if k is None:
                continue
            p1 = cs[k + 1]["c"] if k + 1 < len(cs) else None
            res = rules.stop_target(cs, k, r["dir"], ind.atr[k]) if ind.atr[k] else None
            if p1 is not None or res:
                upd.append((p1 if r["price1"] is None else r["price1"], res[0] if res else None,
                            res[1] if res else None, ind.atr[k], sym, r["t"], r["rule"]))
        if upd:
            db.executemany("UPDATE rule_signals SET price1=?, rr=?, held=?, atr=? WHERE metal=? AND tf='1d' AND t=? "
                           "AND rule=?", upd)
        db.put(mark, str(cs[-2]["t"]))
    return added
