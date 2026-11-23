"""The Judge (Hakim): scores every forecast when its candle closes and says which method, if any, can be trusted.

Per forecast: outcome (1 up / 0 down; an unchanged close is not scored), hit (direction right; P = 0.5 has no
direction and gets no hit), Brier score, and whether the close fell inside the 50 % and 80 % ranges.
Per method: hit rate against «Həmişə yuxarı», Brier skill against a coin (0.25), range coverage, and a status:
- "az"      fewer scored forecasts than MIN_N: no verdict yet
- "sübut"   beats the better baseline on hit rate with one-sided p < 0.05 / (number of methods) AND Brier skill > 0
            AND its average move in the forecast's direction is larger than the bid/ask spread
- "xərc"    statistically real but smaller than the spread: no use for trading
- "yox"     enough forecasts, no proof of skill"""
from __future__ import annotations

import math
import time

from .db import DB
from . import candles
from .forecast import BASELINES, HORIZON_SPEC, methods_for, steps_of, target_time

# A round trip costs about one bid/ask spread (Capital.com, seen in diagnostics 2026-11-23: gold 0.50 $ on 3600 $,
# silver 0.05 on 42, platinum 6 on 1318, palladium 5 on 904). A direction is worth something only if the average
# move in the forecast's direction is larger than this.
COST = {"XAU": 0.00014, "XAG": 0.0012, "XPT": 0.0046, "XPD": 0.0055}
MIN_N = {"1m": 300, "1h": 200, "4h": 200, "1d": 250, "3d": 250, "1w": 100, "10d": 250, "1mo": 250}
P_MAX = 0.05


def issue_rows(symbol: str, horizon: str, issued_t: int, target_t: int, fc: dict, mode: str = "live") -> list:
    return [(symbol, horizon, m, mode, issued_t, target_t, fc["price"], v["p_up"], v["lo50"], v["hi50"],
             v["lo80"], v["hi80"], v["basis"]) for m, v in fc["methods"].items()]


def insert(db: DB, rows: list) -> None:
    db.executemany(
        "INSERT OR IGNORE INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, "
        "lo50, hi50, lo80, hi80, basis) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def issue(db: DB, symbol: str, horizon: str, issued_t: int, target_t: int, fc: dict, mode: str = "live") -> int:
    rows = issue_rows(symbol, horizon, issued_t, target_t, fc, mode)
    db.executemany(
        "INSERT OR IGNORE INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, "
        "lo50, hi50, lo80, hi80, basis) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def score_row(price0: float, price1: float, p_up: float, lo50: float, hi50: float, lo80: float, hi80: float) -> dict:
    in50 = int(lo50 <= price1 <= hi50)
    in80 = int(lo80 <= price1 <= hi80)
    if price1 == price0:
        return {"outcome": None, "hit": None, "brier": None, "in50": in50, "in80": in80}
    outcome = int(price1 > price0)
    hit = None if p_up == 0.5 else int((p_up > 0.5) == bool(outcome))
    return {"outcome": outcome, "hit": hit, "brier": (p_up - outcome) ** 2, "in50": in50, "in80": in80}


def score_due(db: DB, now: float | None = None) -> int:
    """Score every open forecast whose target candle has closed. The target is the k-th candle from the issue candle
    on (k = candles ahead of the horizon): one query per horizon finds it through the candles' primary key."""
    now = time.time() if now is None else now
    updates, dropped, n_done = [], [], 0
    for h, (tf, k) in HORIZON_SPEC.items():
        step = candles.TF[tf]
        sub = ("(SELECT {col} FROM candles c WHERE c.symbol=f.symbol AND c.tf=? AND c.t>=f.issued_t "
               "ORDER BY c.t LIMIT 1 OFFSET ?)")
        cur = db.execute(
            "SELECT f.id, f.issued_t, f.target_t, f.price0, f.p_up, f.lo50, f.hi50, f.lo80, f.hi80, "
            f"{sub.format(col='c.c')} AS close1, {sub.format(col='c.t')} AS t1 "
            "FROM forecasts f WHERE f.horizon=? AND f.scored_ts IS NULL AND f.target_t <= ?",
            (tf, k - 1, tf, k - 1, h, now))
        # Read in chunks: after a history replay there can be 100 000+ open rows and the server has 512 MB.
        rows = iter(lambda: cur.fetchmany(5000), [])
        rows = (r for chunk in rows for r in chunk)
        for r in rows:
            t1 = r["t1"]
            # The target is exactly the expected candle; for daily candles the expected weekday (weekends skipped),
            # with two days of grace for market holidays.
            latest = (target_time(r["issued_t"], h) - step + 2 * 86400) if tf == "1d" else r["issued_t"] + (k - 1) * step
            ok = t1 is not None and t1 + step <= now and t1 <= latest
            if not ok:
                # No candle for the target (market closed, feed gap): dropped after a while, never guessed.
                if now - r["target_t"] > (86400 if tf not in ("1d", "1w") else 10 * 86400):
                    dropped.append((now, r["id"]))
                continue
            s = score_row(r["price0"], r["close1"], r["p_up"], r["lo50"], r["hi50"], r["lo80"], r["hi80"])
            updates.append((r["close1"], now, s["outcome"], s["hit"], s["brier"], s["in50"], s["in80"], r["id"]))
        if len(updates) >= 20000:      # the cursor of this horizon is fully read: writing now is safe
            _write(db, updates, dropped)
            n_done += len(updates)
            updates, dropped = [], []
    n_done += len(updates)
    _write(db, updates, dropped)
    return n_done


def _write(db: DB, updates: list, dropped: list) -> None:
    if updates:
        db.executemany("UPDATE forecasts SET price1=?, scored_ts=?, outcome=?, hit=?, brier=?, in50=?, in80=? "
                       "WHERE id=?", updates)
    if dropped:
        db.executemany("UPDATE forecasts SET scored_ts=? WHERE id=?", dropped)


def _p_one_sided(hits: int, n: int, p0: float) -> float:
    """P(at least `hits` of n | true rate p0), normal approximation with continuity correction."""
    if n == 0 or p0 <= 0 or p0 >= 1:
        return 1.0
    z = (hits - 0.5 - n * p0) / math.sqrt(n * p0 * (1 - p0))
    return 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))


_STATS_CACHE: dict = {}


def stats(db: DB, symbol: str, horizon: str, mode: str = "live", ttl: float = 0) -> list[dict]:
    """ttl > 0: an answer up to ttl seconds old is reused (the panel asks every 20 s; a month of one-minute
    forecasts is ~400 000 rows per metal, too much to count again on every request)."""
    key = (id(db), symbol, horizon, mode)
    hit = _STATS_CACHE.get(key)
    if ttl and hit and time.time() - hit[0] < ttl:
        return hit[1]
    out = _stats(db, symbol, horizon, mode)
    _STATS_CACHE[key] = (time.time(), out)
    return out


def _stats(db: DB, symbol: str, horizon: str, mode: str) -> list[dict]:
    q = ("SELECT method, COUNT(outcome) n, SUM(outcome) ups, COUNT(hit) nh, SUM(hit) hits, AVG(brier) brier, "
         "AVG(in50) c50, AVG(in80) c80, COUNT(price1) ncov, "
         # average move in the forecast's direction (only forecasts with a view), as a fraction of the price
         "AVG(CASE WHEN p_up > 0.5 THEN price1 / price0 - 1 WHEN p_up < 0.5 THEN 1 - price1 / price0 END) edge "
         "FROM forecasts "
         "WHERE symbol=? AND horizon=? AND mode=? AND scored_ts IS NOT NULL GROUP BY method")
    rows = {r["method"]: dict(r) for r in db.execute(q, (symbol, horizon, mode)).fetchall()}
    base_up = rows.get("up", {})
    up_rate = (base_up.get("ups") or 0) / base_up["n"] if base_up.get("n") else None
    out = []
    k = steps_of(horizon)
    # Many methods are tried on the same data: by chance one in twenty passes p < 0.05. Bonferroni: the bar is
    # divided by the number of methods competing on this card.
    tested = [m for m in methods_for(horizon) if m not in BASELINES]
    p_bar = P_MAX / max(1, len(tested))
    cost = COST.get(symbol, 0.0)
    for m in methods_for(horizon):
        r = rows.get(m) or {"n": 0, "nh": 0, "hits": 0, "brier": None, "c50": None, "c80": None}
        n, nh, hits = r["n"] or 0, r["nh"] or 0, r["hits"] or 0
        hit_rate = hits / nh if nh else None
        bss = 1 - r["brier"] / 0.25 if r["brier"] is not None else None
        # Beat the better of a coin (0.5) and «always up» on the same forecasts.
        bar = max(0.5, up_rate if up_rate is not None else 0.5, 1 - (up_rate or 0.5))
        # Forecasts k candles ahead, issued every candle, overlap: k neighbours share most of their path, so they
        # count as about one independent test. The p-value uses that effective number, not the raw count.
        p = _p_one_sided(round(hits / k), round(nh / k), bar) if nh >= k else None
        if m in BASELINES:
            status = "bazis"
        elif nh < MIN_N[horizon]:
            status = "az"
        elif p is not None and p < p_bar and bss is not None and bss > 0:
            # Real statistically, but is the average move bigger than the spread? If not, it cannot pay.
            status = "sübut" if (r.get("edge") or 0) > cost else "xərc"
        else:
            status = "yox"
        out.append({"method": m, "n": n, "hit_rate": hit_rate, "bar": bar, "p": p, "brier": r["brier"],
                    "bss": bss, "cover50": r["c50"], "cover80": r["c80"], "status": status, "nh": nh,
                    "min_n": MIN_N[horizon], "p_bar": p_bar, "edge": r.get("edge"), "cost": cost})
    return out


def official(stat_rows: list[dict]) -> dict:
    """The card's verdict: the proven method with the best Brier skill, or none."""
    proven = [r for r in stat_rows if r["status"] == "sübut"]
    if proven:
        best = max(proven, key=lambda r: r["bss"])
        return {"method": best["method"], "status": "sübut"}
    if any(r["status"] == "yox" for r in stat_rows):
        return {"method": "rw", "status": "yox"}
    return {"method": "rw", "status": "az"}


def series(db: DB, symbol: str, horizon: str, mode: str, window: int = 100, points: int = 120) -> dict:
    """How accuracy moved over time: for each method a rolling hit rate over its last `window` judged forecasts, and
    the rolling share of closes inside the 50 % and 80 % ranges (the same ranges for every method: taken from rw)."""
    out = {"methods": {}, "cover": {}}
    # Recent window only: a month of one-minute forecasts is ~400 000 rows; the chart needs the recent trend.
    span = {"1m": 3 * 86400, "1h": 120 * 86400, "4h": 365 * 86400}.get(horizon)
    since = (time.time() - span) if (span and mode == "live") else 0
    rows = db.execute("SELECT method, target_t, hit, in50, in80 FROM forecasts WHERE symbol=? AND horizon=? AND mode=? "
                      "AND scored_ts IS NOT NULL AND price1 IS NOT NULL AND target_t > ? ORDER BY target_t",
                      (symbol, horizon, mode, since)).fetchall()
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["method"], []).append(r)

    def roll(seq, key):
        res, acc, buf = [], 0, []
        for r in seq:
            buf.append(r[key])
            acc += r[key]
            if len(buf) > window:
                acc -= buf.pop(0)
            if len(buf) >= min(window, 20):
                res.append((r["target_t"], acc / len(buf)))
        if len(res) > points:
            stepn = len(res) / points
            res = [res[int(i * stepn)] for i in range(points - 1)] + [res[-1]]
        return [[t, round(v, 4)] for t, v in res]

    for m, seq in by.items():
        judged = [r for r in seq if r["hit"] is not None]
        if m not in BASELINES and judged:
            out["methods"][m] = roll(judged, "hit")
    base = by.get("rw", [])
    out["cover"] = {"50": roll(base, "in50"), "80": roll(base, "in80")}
    out["window"] = window
    return out


def overview(db: DB, symbol: str, mode: str) -> list[dict]:
    """One row per horizon: each method's hit rate and status, and the range coverage. The page's summary matrix."""
    from .forecast import HORIZONS
    return [{"horizon": h, "stats": stats(db, symbol, h, mode)} for h in HORIZONS]


def where(db: DB, symbol: str, horizon: str, mode: str) -> dict:
    """Where each method is right and where it misses: by trading session (intraday horizons only) and by market
    mood (calm vs wild: the forecast's own 80 % range width against its average). Shows WHY a method fails, e.g.
    "works in calm markets, loses in wild ones" or "only the New York session" — the hint for the next fix."""
    intraday = HORIZON_SPEC[horizon][0] in ("1m", "1h", "4h")
    avg = db.execute("SELECT AVG((hi80 - lo80) / price0) w FROM forecasts WHERE symbol=? AND horizon=? AND mode=? "
                     "AND method='rw' AND scored_ts IS NOT NULL", (symbol, horizon, mode)).fetchone()["w"]
    if avg is None:
        return {"groups": [], "methods": {}}
    rows = db.execute(
        "SELECT method, "
        "CASE WHEN (issued_t / 3600) % 24 >= 22 OR (issued_t / 3600) % 24 < 7 THEN 'asia' "
        "     WHEN (issued_t / 3600) % 24 < 13 THEN 'london' ELSE 'ny' END sess, "
        "CASE WHEN (hi80 - lo80) / price0 > ? THEN 'wild' ELSE 'calm' END mood, "
        "COUNT(hit) n, SUM(hit) k FROM forecasts WHERE symbol=? AND horizon=? AND mode=? AND scored_ts IS NOT NULL "
        "AND hit IS NOT NULL AND method NOT IN ('rw', 'up') GROUP BY method, sess, mood",
        (avg, symbol, horizon, mode)).fetchall()
    groups = (["asia", "london", "ny"] if intraday else []) + ["calm", "wild"]
    out: dict[str, dict] = {}
    for r in rows:
        m = out.setdefault(r["method"], {g: [0, 0] for g in groups})
        for g in ((r["sess"],) if intraday else ()) + (r["mood"],):
            m[g][0] += r["n"]
            m[g][1] += r["k"] or 0
    return {"groups": groups, "methods": {m: {g: {"n": v[0], "hit_rate": v[1] / v[0] if v[0] else None}
                                              for g, v in d.items()} for m, d in out.items()}}
