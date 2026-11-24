"""Öyrənmə (Block 11): how the system learns from its own outcomes, modelled on dopamine and sleep.

1. Hedge (reward-prediction error): on each desk every analyst's weight is multiplied by exp(ETA * (hit - bar)) for each
   of its resolved forecasts, oldest first, over a recent window: better than expected -> heavier, worse -> lighter.
   A floor (FLOOR x the best) keeps a temporarily wrong analyst able to come back. The scale (tərəzi) uses an analyst
   only if it is recently better than the average analyst (relative weight > 1.05) AND not below the bar in the long
   run (Judge z >= 0): recency without forgetting the long record.
2. Calibration: a brain that says 65 % should be right 65 % of the time. From its scored views (honest scoring,
   brainviews.score rules), each probability band's real up-rate replaces the brain's number once the band has 30+
   cases, shrunk towards the brain's own number (20 pseudo-cases). Recomputed nightly.
3. Sleep (nightly review): the day's biggest brain errors (with the reasons the brains gave and what the price did)
   go to one brain, which writes at most 3 short lessons from those facts only. The lessons are tested, not trusted:
   the second analyst gets them on EVEN days only (A/B by day), and its hit rate on even and odd days is compared.
   Lessons older than 7 days are retired."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone

from .db import DB

ETA, FLOOR = 0.05, 0.05
MAX_ROWS = 20000
WINDOW = {"15m": 20, "30m": 30, "1h": 60, "4h": 180, "1d": 1100, "3d": 1100, "1w": 1100, "10d": 1100, "1mo": 1100}
SKIP = ("rw", "up", "consensus", "terazi", "vahid")
BANDS = [(0.0, 0.40), (0.40, 0.48), (0.52, 0.60), (0.60, 1.01)]
LESSONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (id INTEGER PRIMARY KEY, ts REAL NOT NULL, text TEXT NOT NULL, active INTEGER DEFAULT 1);
"""


def hedge(db: DB, symbol: str, horizon: str, now: float | None = None) -> dict[str, float]:
    """Relative weights (mean 1) after replaying the recent resolved forecasts of this desk, oldest first."""
    now = time.time() if now is None else now
    since = now - WINDOW.get(horizon, 365) * 86400
    # the newest MAX_ROWS results only (newest first from the index, then replayed oldest first): bounded memory
    rows = db.execute("SELECT method, hit, outcome FROM forecasts WHERE symbol=? AND horizon=? AND hit IS NOT NULL "
                      "AND issued_t > ? ORDER BY issued_t DESC LIMIT ?", (symbol, horizon, since, MAX_ROWS)).fetchall()
    rows.reverse()
    if not rows:
        return {}
    ups = [r["outcome"] for r in rows if r["outcome"] is not None]
    up_rate = sum(ups) / len(ups) if ups else 0.5
    bar = max(0.5, up_rate, 1 - up_rate)
    logw: dict[str, float] = {}
    for r in rows:
        m = r["method"]
        if m in SKIP:
            continue
        logw[m] = logw.get(m, 0.0) + ETA * ((1.0 if r["hit"] else 0.0) - bar)
        top = max(logw.values())
        floor = top + math.log(FLOOR)
        if logw[m] < floor:
            logw[m] = floor                       # never below FLOOR x the best: it can come back
    if not logw:
        return {}
    w = {m: math.exp(v - max(logw.values())) for m, v in logw.items()}
    mean = sum(w.values()) / len(w)
    return {m: round(v / mean, 3) for m, v in w.items()}


def combine(hedge_rel: dict[str, float], z_rows: list[dict], k: int) -> dict[str, float]:
    """The scale's weights: recently better than average (hedge > 1.05) and not below the bar in the long run."""
    z_of = {}
    for r in z_rows:
        hr, nh, bar = r.get("hit_rate"), r.get("nh") or 0, r.get("bar") or 0.5
        if hr is not None and nh >= 30:
            z_of[r["method"]] = (hr - bar) / math.sqrt(bar * (1 - bar) / max(1.0, nh / max(1, k)))
    return {m: round(min(3.0, h), 2) for m, h in hedge_rel.items() if h > 1.05 and z_of.get(m, -1) >= 0}


# ---------- calibration ----------
def calibrate(db: DB, now: float | None = None) -> dict:
    """Per brain and horizon: [(lo, hi, observed up-rate, n)] from honestly scored views (last 90 days)."""
    from . import brainviews
    now = time.time() if now is None else now
    brainviews.ensure(db)
    rows = db.execute("SELECT known_ts, source, metal, horizon, p FROM brain_views WHERE known_ts IS NOT NULL AND "
                      "horizon IS NOT NULL AND p IS NOT NULL AND known_ts > ?", (now - 90 * 86400,)).fetchall()

    def px(sym, t):
        r = db.execute("SELECT c FROM candles WHERE symbol=? AND tf='1m' AND t<=? AND t>? ORDER BY t DESC LIMIT 1",
                       (sym, t - 60, t - 1800)).fetchone()
        return r["c"] if r else None
    agg: dict[tuple, list] = {}
    for r in rows:
        end = r["known_ts"] + brainviews.H_SEC.get(r["horizon"], 0)
        if end > now:
            continue
        a, b = px(r["metal"], r["known_ts"]), px(r["metal"], end)
        if not a or not b or a == b:
            continue
        for lo, hi in BANDS:
            if lo <= r["p"] < hi:
                agg.setdefault((r["source"], r["horizon"], lo, hi), []).append(int(b > a))
    out: dict[str, list] = {}
    for (src, h, lo, hi), v in agg.items():
        out.setdefault(f"{src}:{h}", []).append([lo, hi, sum(v) / len(v), len(v)])
    db.put("calib", json.dumps({"ts": now, "bands": out}))
    return out


def apply_calibration(bands: dict, source: str, horizon: str, p: float) -> float:
    for lo, hi, obs, n in bands.get(f"{source}:{horizon}", []):
        if lo <= p < hi and n >= 30:
            return round((n * obs + 20 * p) / (n + 20), 4)
    return p


# ---------- sleep ----------
LESSON_SYSTEM = (
    "You review a precious-metals desk's forecasting errors of the last day. You get the biggest errors: what each "
    "brain predicted, the reason it gave, and what the price then did. Write at most 3 short, general, testable "
    "lessons (one sentence each) that would have avoided these errors. Use ONLY the facts given; no numbers that are "
    "not in them; no trading advice. If the errors show no pattern, return an empty list.")
LESSON_SCHEMA_JSON = {"type": "object", "additionalProperties": False, "required": ["lessons"],
                      "properties": {"lessons": {"type": "array", "items": {"type": "string"}}}}


def day_errors(db: DB, now: float) -> list[dict]:
    from . import brainviews
    rows = db.execute("SELECT known_ts, source, metal, horizon, p, note FROM brain_views WHERE known_ts BETWEEN ? AND ? "
                      "AND horizon='1h' AND ABS(p - 0.5) >= 0.08", (now - 86400 - 3600, now - 3600)).fetchall()
    out = []
    for r in rows:
        a = db.execute("SELECT c FROM candles WHERE symbol=? AND tf='1m' AND t<=? ORDER BY t DESC LIMIT 1",
                       (r["metal"], r["known_ts"] - 60)).fetchone()
        b = db.execute("SELECT c FROM candles WHERE symbol=? AND tf='1m' AND t<=? ORDER BY t DESC LIMIT 1",
                       (r["metal"], r["known_ts"] + brainviews.H_SEC["1h"] - 60)).fetchone()
        if not a or not b or a["c"] == b["c"]:
            continue
        move = b["c"] / a["c"] - 1
        if (move > 0) != (r["p"] > 0.5):
            out.append({"brain": r["source"], "metal": r["metal"], "said_up_prob": r["p"],
                        "reason": (r["note"] or "").split(" · ")[-1][:200], "move_pct_next_hour": round(move * 100, 3),
                        "size": abs(r["p"] - 0.5) * abs(move)})
    return sorted(out, key=lambda x: -x["size"])[:8]


def active_lessons(db: DB, now: float | None = None) -> list[str]:
    db.script(LESSONS_SCHEMA)
    now = time.time() if now is None else now
    return [r["text"] for r in db.execute("SELECT text FROM lessons WHERE active=1 AND ts > ? ORDER BY ts DESC LIMIT 3",
                                          (now - 7 * 86400,)).fetchall()]


def lessons_today(db: DB, now: float | None = None) -> bool:
    """A/B by day: the second analyst gets the lessons on even UTC days only."""
    now = time.time() if now is None else now
    return datetime.fromtimestamp(now, timezone.utc).toordinal() % 2 == 0


def ab_report(db: DB, now: float | None = None, since: float | None = None, until: float | None = None) -> dict:
    """The second analyst's 1-hour hit rate on lesson days vs other days (honest scoring)."""
    from . import brainviews
    brainviews.ensure(db)
    now = time.time() if now is None else now
    out = {"with": [0, 0], "without": [0, 0]}
    for r in db.execute("SELECT known_ts, metal, p FROM brain_views WHERE source='brain2' AND horizon='1h' AND "
                        "known_ts > ? AND known_ts < ? AND ABS(p - 0.5) >= 0.02",
                        (since if since is not None else now - 60 * 86400, until if until is not None else now)).fetchall():
        end = r["known_ts"] + 3600
        if end > now:
            continue
        a = db.execute("SELECT c FROM candles WHERE symbol=? AND tf='1m' AND t<=? ORDER BY t DESC LIMIT 1",
                       (r["metal"], r["known_ts"] - 60)).fetchone()
        b = db.execute("SELECT c FROM candles WHERE symbol=? AND tf='1m' AND t<=? ORDER BY t DESC LIMIT 1",
                       (r["metal"], end - 60)).fetchone()
        if not a or not b or a["c"] == b["c"]:
            continue
        g = out["with" if lessons_today(db, r["known_ts"]) else "without"]
        g[0] += 1
        g[1] += int((b["c"] > a["c"]) == (r["p"] > 0.5))
    return {k: {"n": v[0], "hit_rate": v[1] / v[0] if v[0] else None} for k, v in out.items()}


# ---------- Block 29: rule proposals (a lesson is a proposed rule; it must pass a test before it counts) ----------
PROPOSALS_SCHEMA = """
CREATE TABLE IF NOT EXISTS rule_proposals (id INTEGER PRIMARY KEY, ts REAL NOT NULL, text TEXT NOT NULL,
  status TEXT NOT NULL, decided_ts REAL, evidence TEXT);
"""
MIN_AB = 30          # per arm, within the proposal's own week


def judge_proposals(db: DB, now: float | None = None) -> int:
    """After 7 days a proposal is decided by the A/B test it ran in: the second analyst with the lessons (even days)
    against without (odd days), on its honestly scored 1-hour views. Accepted only if «with» beats «without» by at
    least 3 points on 60+ views each; otherwise rejected (and the reason is kept)."""
    db.script(PROPOSALS_SCHEMA)
    now = time.time() if now is None else now
    n = 0
    for r in db.execute("SELECT id, ts FROM rule_proposals WHERE decided_ts IS NULL AND ts < ?",
                        (now - 7 * 86400,)).fetchall():
        # measured only on the week the proposal was in use (lessons are given for 7 days, on even days)
        ab = ab_report(db, now, since=r["ts"], until=r["ts"] + 7 * 86400)
        w, wo = ab["with"], ab["without"]
        if w["n"] >= MIN_AB and wo["n"] >= MIN_AB and w["hit_rate"] is not None and wo["hit_rate"] is not None:
            ok = w["hit_rate"] - wo["hit_rate"] >= 0.03
            status = "qəbul (A/B-də daha yaxşı)" if ok else "rədd (A/B-də fayda yoxdur)"
        else:
            status = "rədd (sınaq üçün məlumat azdır)"
        db.execute("UPDATE rule_proposals SET status=?, decided_ts=?, evidence=? WHERE id=?",
                   (status, now, json.dumps(ab), r["id"]))
        n += 1
    return n


def accepted_rules(db: DB) -> list[dict]:
    """Proposals that passed their test become house rules («Öyrənilmiş»), given to the brains with the rulebook."""
    db.script(PROPOSALS_SCHEMA)
    return [{"id": f"LRN-{r['id']}", "area": "Öyrənilmiş", "name": "Sınaqdan keçmiş dərs", "how": r["text"],
             "signal": "dərsdə yazıldığı kimi", "void": "yeni sınaq pisləşsə", "source": "öz gecə yoxlamamız + A/B sınağı",
             "detector": False}
            for r in db.execute("SELECT id, text FROM rule_proposals WHERE status LIKE 'qəbul%' ORDER BY ts").fetchall()]
