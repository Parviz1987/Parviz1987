"""The brains as forecasters, judged like every other method (no brain decides anything by itself).

- news      «Xəbər əhvalı»: the Reader's labels (metal, up/down, strength 0-3) on headlines labelled in the window
            before the forecast, summed per metal. Needs at least a clear sum (|score| >= 2) for a view.
- strateq   «Strateqin fikri»: the Strategist's own probability that the metal is higher in 1 hour, 4 hours and 1 day,
            from its latest hourly note written before the forecast (one row per metal and horizon). Older notes
            (before 2026-11-24) only had a lean up / down / neutral; they still count for 4 h and 1 day.
- brain2    «İkinci beyin»: the same question and facts to a brain of another company (OpenAI), on its own: if two
            brains agree it shows in the consensus; each is judged alone.
All use only what was written BEFORE the forecast's issue time (60 s margin)."""
from __future__ import annotations

import bisect

from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS brain_views (ts REAL NOT NULL, source TEXT NOT NULL, metal TEXT NOT NULL,
  lean INTEGER NOT NULL, note TEXT);
CREATE INDEX IF NOT EXISTS brain_views_ts ON brain_views(source, metal, ts);
"""
P_CLIP = (0.3, 0.7)          # a brain's probability is capped: one hour's view never counts as near-certain


def ensure(db: DB) -> None:
    db.conn.executescript(SCHEMA)
    cols = {r[1] for r in db.execute("PRAGMA table_info(brain_views)").fetchall()}
    if "horizon" not in cols:
        db.execute("ALTER TABLE brain_views ADD COLUMN horizon TEXT")
    if "p" not in cols:
        db.execute("ALTER TABLE brain_views ADD COLUMN p REAL")
NEWS_WINDOW = {"15m": 3600, "30m": 3600, "1h": 2 * 3600, "4h": 6 * 3600, "1d": 86400}
STRATEQ_FOR = {"1h": 75 * 60, "4h": 3 * 3600, "1d": 6 * 3600}   # horizon -> how old the Strategist's note may be


class Lookup:
    def __init__(self, db: DB):
        ensure(db)
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
        # (metal, horizon) -> times and probabilities; a lean-only note maps to 0.6 / 0.4 / 0.5 for 4 h and 1 day
        self.strat: dict[tuple[str, str, str], tuple[list[float], list[float]]] = {}
        for r in db.execute("SELECT ts, source, metal, lean, horizon, p FROM brain_views "
                            "WHERE source IN ('strateq', 'brain2') ORDER BY ts").fetchall():
            if r["horizon"]:
                targets = [(r["horizon"], r["p"])]
            else:
                p = 0.5 + 0.1 * int(r["lean"])
                targets = [("4h", p), ("1d", p)]
            for h, p in targets:
                ts, vs = self.strat.setdefault((r["source"], r["metal"], h), ([], []))
                ts.append(r["ts"])
                vs.append(float(p if p is not None else 0.5))

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
            for src, who in (("strateq", "Strateq"), ("brain2", "İkinci beyin")):
                ts, vs = self.strat.get((src, metal, horizon), ([], []))
                i = bisect.bisect_right(ts, t - 60) - 1
                if i < 0 or t - ts[i] > age:
                    out[src] = (0.5, f"{who}: yeni fikir yoxdur")
                elif abs(vs[i] - 0.5) < 0.02:
                    out[src] = (0.5, f"{who} bilmir deyir (50 %)")
                else:
                    p = round(min(max(vs[i], P_CLIP[0]), P_CLIP[1]), 4)
                    out[src] = (p, f"{who}: yuxarı ehtimalı {round(vs[i] * 100)} %")
        return out


H_SEC = {"1h": 3600, "4h": 4 * 3600, "1d": 86400}


def score(db: DB, now: float, days: int = 30) -> list[dict]:
    """The brains' own report card: every probability a brain gave (not 50 %), checked against the price that
    followed (one-minute closes: the last minute ended by the time). Split by brain, by alarm versus the hourly
    run, and by horizon. Views given minutes apart about one event are not independent: a first look, not proof."""
    ensure(db)
    rows = db.execute("SELECT ts, source, metal, horizon, p, note FROM brain_views WHERE horizon IS NOT NULL "
                      "AND p IS NOT NULL AND ABS(p - 0.5) >= 0.02 AND ts > ?", (now - days * 86400,)).fetchall()

    def px(sym: str, t: float) -> float | None:
        r = db.execute("SELECT c FROM candles WHERE symbol=? AND tf='1m' AND t<=? AND t>? ORDER BY t DESC LIMIT 1",
                       (sym, t - 60, t - 1800)).fetchone()
        return r["c"] if r else None
    agg: dict[tuple, list[int]] = {}
    for r in rows:
        end = r["ts"] + H_SEC.get(r["horizon"], 0)
        if end > now:
            continue
        a, b = px(r["metal"], r["ts"]), px(r["metal"], end)
        if not a or not b or a == b:
            continue
        hit = int((b > a) == (r["p"] > 0.5))
        key = (r["source"], "həyəcan" if (r["note"] or "").startswith("həyəcan") else "saatlıq", r["horizon"])
        agg.setdefault(key, []).append(hit)
    return [{"brain": k[0], "when": k[1], "horizon": k[2], "n": len(v), "hit_rate": sum(v) / len(v)}
            for k, v in sorted(agg.items())]
