"""The brains as forecasters, judged like every other method (no brain decides anything by itself).

- news      «Xəbər əhvalı»: the Reader's labels (metal, up/down, strength 0-3) on headlines labelled in the window
            before the forecast, summed per metal. Needs at least a clear sum (|score| >= 2) for a view.
- strateq   «Strateqin fikri»: the Strategist's own lean per metal (up / down / neutral), from its latest hourly
            note written before the forecast (for the 4-hour and 1-day desks).
Both use only what was written BEFORE the forecast's issue time (60 s margin)."""
from __future__ import annotations

import bisect

from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS brain_views (ts REAL NOT NULL, source TEXT NOT NULL, metal TEXT NOT NULL,
  lean INTEGER NOT NULL, note TEXT);
CREATE INDEX IF NOT EXISTS brain_views_ts ON brain_views(source, metal, ts);
"""
NEWS_WINDOW = {"15m": 3600, "30m": 3600, "1h": 2 * 3600, "4h": 6 * 3600, "1d": 86400}
STRATEQ_FOR = {"4h": 3 * 3600, "1d": 6 * 3600}       # horizon -> how old the Strategist's note may be


class Lookup:
    def __init__(self, db: DB):
        db.conn.executescript(SCHEMA)
        self.news: dict[str, tuple[list[float], list[int]]] = {}
        try:
            rows = db.execute("SELECT ts, metals, direction, strength FROM news_ai WHERE direction IN ('up', 'down') "
                              "AND strength > 0 ORDER BY ts").fetchall()
        except Exception:
            rows = []
        for r in rows:
            v = int(r["strength"]) * (1 if r["direction"] == "up" else -1)
            for m in (r["metals"] or "").split(","):
                ts, vs = self.news.setdefault(m, ([], []))
                ts.append(r["ts"])
                vs.append(v)
        self.strat: dict[str, tuple[list[float], list[int]]] = {}
        for r in db.execute("SELECT ts, metal, lean FROM brain_views WHERE source='strateq' ORDER BY ts").fetchall():
            ts, vs = self.strat.setdefault(r["metal"], ([], []))
            ts.append(r["ts"])
            vs.append(int(r["lean"]))

    def views(self, metal: str, t: float, horizon: str) -> dict:
        out = {}
        w = NEWS_WINDOW.get(horizon)
        if w:
            ts, vs = self.news.get(metal, ([], []))
            if not ts or t < ts[0]:
                out["news"] = (0.5, "Oxuyucunun qiymətləndirməsi hələ yoxdur")
            else:
                lo, hi = bisect.bisect_left(ts, t - w), bisect.bisect_right(ts, t - 60)
                score, n = sum(vs[lo:hi]), hi - lo
                if abs(score) >= 2:
                    p = min(max(0.5 + 0.03 * score, 0.35), 0.65)
                    out["news"] = (round(p, 4), f"son {w // 3600} saatda {n} xəbər: əhval {score:+d} "
                                                f"({'müsbət' if score > 0 else 'mənfi'})")
                else:
                    out["news"] = (0.5, f"son {w // 3600} saatda {n} xəbər: aydın əhval yoxdur ({score:+d})")
        age = STRATEQ_FOR.get(horizon)
        if age:
            ts, vs = self.strat.get(metal, ([], []))
            i = bisect.bisect_right(ts, t - 60) - 1
            if i < 0 or t - ts[i] > age:
                out["strateq"] = (0.5, "Strateqin yeni fikri yoxdur")
            elif vs[i] == 0:
                out["strateq"] = (0.5, "Strateq neytraldır")
            else:
                out["strateq"] = (0.6 if vs[i] > 0 else 0.4,
                                  f"Strateq {'yuxarı' if vs[i] > 0 else 'aşağı'} meyllidir")
        return out
