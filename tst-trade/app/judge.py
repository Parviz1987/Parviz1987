"""The Judge (Hakim): scores every forecast when its candle closes and says which method, if any, can be trusted.

Per forecast: outcome (1 up / 0 down; an unchanged close is not scored), hit (direction right; P = 0.5 has no
direction and gets no hit), Brier score, and whether the close fell inside the 50 % and 80 % ranges.
Per method: hit rate against «Həmişə yuxarı», Brier skill against a coin (0.25), range coverage, and a status:
- "az"      fewer scored forecasts than MIN_N: no verdict yet
- "sübut"   beats the better baseline on hit rate with one-sided p passing Holm's step-down over the direction methods
            (alpha 0.05) AND Brier skill > 0 AND its average move in the forecast's direction is larger than the full cost
            (spread + slippage + overnight financing)
- "xərc"    statistically real but smaller than the full cost: no use for trading
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

# Full cost (Block 15, owner 2026-11-24): the spread is not all a trade pays.
# - slippage: a market order fills a little worse than the price we saw, most of all when the market moves fast.
#   Assumed half a spread per round trip (no fill data yet: we place no orders). SLIP is that share.
# - overnight financing (swap): a CFD held past the broker's daily cut-off pays a fee each night. Capital.com
#   publishes it per market (instrument.overnightFee, % per day); engine stores what the broker says in SWAP. Until
#   it has been read, SWAP_GUESS per day is used and the cost is marked «təxmini» (an estimate).
#   A forecast issued every candle holds on average H / 24 h nights, so a 4-hour view pays 1/6 of a night, a week
#   7 nights.
SLIP = 0.5
SWAP_GUESS = 0.0002
SWAP: dict[str, float] = {}          # symbol -> fraction of the price paid per night (average of long and short)
HOLD_DAYS = {"15m": 1 / 96, "30m": 1 / 48, "1h": 1 / 24, "4h": 1 / 6, "1d": 1.0, "3d": 4.2, "1w": 7.0, "10d": 14.0,
             "1mo": 30.0}


def set_swap(rates: dict[str, float]) -> None:
    SWAP.clear()
    SWAP.update({k: float(v) for k, v in rates.items() if v is not None and 0 <= float(v) < 0.01})


def full_cost(symbol: str, horizon: str | None = None) -> float:
    """What one forecast's trade really costs, as a fraction of the price: spread + slippage + the nights it holds."""
    spread = COST.get(symbol, 0.0)
    nights = HOLD_DAYS.get(horizon, 0.0) if horizon else 0.0
    return spread * (1 + SLIP) + nights * SWAP.get(symbol, SWAP_GUESS)


def cost_parts(symbol: str, horizon: str | None = None) -> dict:
    spread = COST.get(symbol, 0.0)
    nights = HOLD_DAYS.get(horizon, 0.0) if horizon else 0.0
    sw = SWAP.get(symbol)
    return {"spread": spread, "slip": spread * SLIP, "swap": nights * (sw if sw is not None else SWAP_GUESS),
            "swap_source": "broker" if sw is not None else ("təxmini" if nights else None),
            "total": full_cost(symbol, horizon)}
MIN_N = {"15m": 300, "30m": 250, "1h": 200, "4h": 200, "1d": 250, "3d": 250, "1w": 100, "10d": 250, "1mo": 250}
P_MAX = 0.05
RANGE_ONLY = ("garch", "gvz")


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
    # The family: methods that give a DIRECTION (range-only methods — GARCH, GVZ — make no direction claim and are
    # judged on their ranges, not counted here). Holm's step-down (2026-11-24) instead of plain Bonferroni: the same
    # protection against luck across many methods, but the best method is not held to the bar of the worst.
    tested = [m for m in methods_for(horizon) if m not in BASELINES and m not in RANGE_ONLY]
    p_bar = P_MAX / max(1, len(tested))
    cost = full_cost(symbol, horizon)
    parts = cost_parts(symbol, horizon)
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
        if m in BASELINES or m in RANGE_ONLY:
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
                    "min_n": MIN_N[horizon], "p_bar": p_bar, "edge": r.get("edge"), "cost": cost,
                    "cost_parts": parts})
    _holm(out, P_MAX, len(tested))
    return out


def _holm(rows: list[dict], alpha: float, m: int) -> None:
    """Holm step-down over the direction methods that reached MIN_N with Brier skill > 0: the k-th smallest p is
    compared with alpha / (m - k + 1); once one fails, the rest fail. A method that passes with a move smaller than
    the cost stays «xərc»."""
    fam = [r for r in rows if r["status"] not in ("bazis", "az") and r["method"] not in RANGE_ONLY]
    m = max(m, 1)                      # the whole family counts, also methods that have too few forecasts yet
    cand = sorted((r for r in fam if r["p"] is not None and r["bss"] is not None and r["bss"] > 0),
                  key=lambda r: r["p"])
    passed = True
    for k, r in enumerate(cand):
        bar = alpha / max(1, m - k)
        r["p_bar"] = bar
        if passed and r["p"] < bar:
            r["status"] = "sübut" if (r.get("edge") or 0) > r["cost"] else "xərc"
        else:
            passed = False
            if r["status"] in ("sübut", "xərc"):
                r["status"] = "yox"


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
    span = {"15m": 30 * 86400, "30m": 60 * 86400, "1h": 120 * 86400, "4h": 365 * 86400}.get(horizon)
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


SESSIONS = {"asia": "Asiya", "london": "London", "ny": "Nyu-York"}


def session_of(t: float) -> str:
    h = int(t // 3600) % 24
    return "asia" if h >= 22 or h < 7 else "london" if h < 13 else "ny"


def where(db: DB, symbol: str, horizon: str, mode: str) -> dict:
    """Where each method is right and where it misses: by trading session (intraday horizons only) and by market
    mood (calm vs wild: the forecast's own 80 % range width against its average). Shows WHY a method fails, e.g.
    "works in calm markets, loses in wild ones" or "only the New York session" — the hint for the next fix.

    Each condition also gets a verdict (conditional proof): the same rules as the whole card — enough judged
    forecasts, beat the bar with p < 0.05 divided by (methods x conditions) (Bonferroni over every cell tried), Brier
    skill > 0 and an average move in the forecast's direction larger than the spread."""
    intraday = HORIZON_SPEC[horizon][0] in ("15m", "30m", "1h", "4h")
    avg = db.execute("SELECT AVG((hi80 - lo80) / price0) w FROM forecasts WHERE symbol=? AND horizon=? AND mode=? "
                     "AND method='rw' AND scored_ts IS NOT NULL", (symbol, horizon, mode)).fetchone()["w"]
    if avg is None:
        return {"groups": [], "methods": {}, "avg_width": None}
    rows = db.execute(
        "SELECT method, "
        "CASE WHEN (issued_t / 3600) % 24 >= 22 OR (issued_t / 3600) % 24 < 7 THEN 'asia' "
        "     WHEN (issued_t / 3600) % 24 < 13 THEN 'london' ELSE 'ny' END sess, "
        "CASE WHEN (hi80 - lo80) / price0 > ? THEN 'wild' ELSE 'calm' END mood, "
        "COUNT(hit) n, SUM(hit) k, SUM(brier) b, "
        "SUM(CASE WHEN p_up > 0.5 THEN price1 / price0 - 1 WHEN p_up < 0.5 THEN 1 - price1 / price0 END) e "
        "FROM forecasts WHERE symbol=? AND horizon=? AND mode=? AND scored_ts IS NOT NULL "
        "AND hit IS NOT NULL AND method NOT IN ('rw', 'up') GROUP BY method, sess, mood",
        (avg, symbol, horizon, mode)).fetchall()
    groups = (["asia", "london", "ny"] if intraday else []) + ["calm", "wild"]
    acc: dict[str, dict] = {}
    for r in rows:
        m = acc.setdefault(r["method"], {g: [0, 0, 0.0, 0.0] for g in groups})
        for g in ((r["sess"],) if intraday else ()) + (r["mood"],):
            c = m[g]
            c[0] += r["n"]
            c[1] += r["k"] or 0
            c[2] += r["b"] or 0
            c[3] += r["e"] or 0
    base = {r["method"]: r for r in _stats(db, symbol, horizon, mode)}
    bar = next(iter(base.values()))["bar"] if base else 0.5
    k = steps_of(horizon)
    cells = max(1, len([m for m in methods_for(horizon) if m not in BASELINES and m not in RANGE_ONLY])
                * len(groups))
    p_bar = P_MAX / cells
    cost = full_cost(symbol, horizon)
    out = {}
    for m, d in acc.items():
        out[m] = {}
        for g, (n, hits, brier, edge) in d.items():
            hr = hits / n if n else None
            p = _p_one_sided(round(hits / k), round(n / k), bar) if n >= k else None
            bss = 1 - (brier / n) / 0.25 if n else None
            e = edge / n if n else None
            if n < MIN_N[horizon]:
                st = "az"
            elif p is not None and p < p_bar and bss is not None and bss > 0:
                st = "sübut" if (e or 0) > cost else "xərc"
            else:
                st = "yox"
            out[m][g] = {"n": n, "hit_rate": hr, "p": p, "edge": e, "status": st}
    return {"groups": groups, "methods": out, "avg_width": avg, "bar": bar, "p_bar": p_bar, "cost": cost}


def conditional(where_result: dict, session: str | None, width: float | None) -> dict | None:
    """The best method proven for the conditions right now (this session, this market mood), or None."""
    if not where_result.get("methods"):
        return None
    now = []
    if session in where_result["groups"]:
        now.append(session)
    if width is not None and where_result.get("avg_width"):
        now.append("wild" if width > where_result["avg_width"] else "calm")
    best = None
    for m, d in where_result["methods"].items():
        for g in now:
            c = d.get(g)
            if c and c["status"] == "sübut" and (best is None or c["hit_rate"] > best["hit_rate"]):
                best = {"method": m, "group": g, **c}
    return best


# ---------- one verdict (2026-11-24 audit: the card, the decision strip, the outlook and the brains' facts each used
# to decide «proven or not» their own way and could disagree) ----------
_WHERE: dict = {}


def where_cached(db: DB, symbol: str, horizon: str, mode: str, now: float | None = None, ttl: float = 1800) -> dict:
    """One shared cache for the heavy session/mood grouping (the card, the decision strip and the page all use it)."""
    now = time.time() if now is None else now
    key = (id(db), symbol, horizon, mode)
    hit = _WHERE.get(key)
    if not hit or now - hit[0] > ttl:
        hit = (now, where(db, symbol, horizon, mode))
        _WHERE[key] = hit
    return hit[1]


def mode_of(live: list[dict], horizon: str) -> str:
    """Live once any direction method has MIN_N live forecasts with a view; history until then. One rule for all."""
    enough = any((r.get("nh") or 0) >= MIN_N[horizon] for r in live
                 if r["method"] not in BASELINES and r["method"] not in RANGE_ONLY)
    return "live" if enough else "history"


def verdict(db: DB, symbol: str, horizon: str, now: float | None = None) -> dict:
    """THE Judge's verdict for a desk: the proven method (overall, or only in the conditions right now: this session or
    this market mood), with the mode it was judged in. Everyone who needs «proven or not» asks here."""
    now = time.time() if now is None else now
    live = stats(db, symbol, horizon, "live", ttl=600)
    mode = mode_of(live, horizon)
    rows = live if mode == "live" else stats(db, symbol, horizon, "history", ttl=600)
    v = official(rows)
    v["by"] = mode
    if v["status"] == "sübut":
        return v
    hit = (now, where_cached(db, symbol, horizon, mode, now))
    rw = db.execute("SELECT lo80, hi80, price0 FROM forecasts WHERE symbol=? AND horizon=? AND mode='live' AND "
                    "method='rw' ORDER BY issued_t DESC LIMIT 1", (symbol, horizon)).fetchone()
    width = (rw["hi80"] - rw["lo80"]) / rw["price0"] if rw and rw["price0"] else None
    cond = conditional(hit[1], session_of(now), width)
    if cond:
        f = db.execute("SELECT p_up FROM forecasts WHERE symbol=? AND horizon=? AND method=? AND mode='live' "
                       "ORDER BY issued_t DESC LIMIT 1", (symbol, horizon, cond["method"])).fetchone()
        if not f or f["p_up"] == 0.5:
            return v                                  # proven in these conditions, but it has no view right now
        return {"method": cond["method"], "status": "sübut", "by": mode, "condition": cond["group"],
                "cond_hit_rate": cond["hit_rate"], "cond_n": cond["n"]}
    return v
