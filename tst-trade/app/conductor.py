"""Dirijor (owner 2026-11-26: «a voice we pushed aside may be needed again some day: how does world practice make the
useful information always come forward?»).

Part 1, the evidence (this file, first): before any market-state weighting is built, the system's own record is read
to see whether the voices really do better in some market states than in others. Each forecast moment gets one state,
known at the moment the forecast was made (closed daily candles before it, the calendar known in advance):

- «hadisə» (event): a high-impact US release (CPI, payrolls, FOMC ...) falls inside the forecast's horizon;
- «şok» (shock): the last 20 days' volatility is in the top 20 % of the past year's;
- «trend»: the last 20 days moved at least one 20-day standard deviation in one direction;
- «yan» (range): none of these.

Per metal, horizon, voice and state: how many views, how many right, the bar of that state (always «up» or always
«down», whichever was better), and on how many separate trading days (forecasts of one day are not independent).
Whether a voice's hit rate really differs between states is tested on trading days, not on forecasts. Nothing here
changes a forecast: it only measures. Recomputed once a day off the event loop; the diagnostics read the stored result."""
from __future__ import annotations

import bisect
import json
import math
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import DB

NY = ZoneInfo("America/New_York")
STATES = ("hadisə", "şok", "trend", "yan")
AUDIT_HORIZONS = ("1h", "4h", "1d", "1w")
SKIP = ("rw", "up", "consensus", "terazi", "vahid", "dirijor")


def _voice(m: str) -> bool:
    """A voice of today: a method in use (the retired ones' old live rows stay in the table but are not voices)."""
    from .forecast import METHODS
    return m in METHODS and m not in SKIP
VOL_N, YEAR_N = 20, 250
SHOCK_PCT, TREND_Z = 0.80, 1.0
MAX_ROWS = 250000                    # newest rows per desk: bounded memory on the 1 GB server
MIN_DAYS = 20                        # a voice/state cell needs at least this many separate trading days to be read
EVENT_RE = ("cpi", "consumer price", "non farm", "nonfarm", "non-farm", "payroll", "fomc", "fed interest rate",
            "interest rate decision", "pce", "gdp")
AUDIT_KEY = "conductor:audit"
VER = "2026-11-26.5"            # a new version recomputes at once instead of waiting a day


# ---------- market state ----------
class Daily:
    """The metal's closed daily candles with the volatility and trend measures, looked up by time."""

    def __init__(self, candles: list[dict]):
        self.t = [c["t"] for c in candles]
        cl = [c["c"] for c in candles]
        r = [0.0] + [math.log(cl[i] / cl[i - 1]) if cl[i - 1] > 0 and cl[i] > 0 else 0.0 for i in range(1, len(cl))]
        self.vol: list[float | None] = [None] * len(cl)
        self.z: list[float | None] = [None] * len(cl)
        self.pct: list[float | None] = [None] * len(cl)
        for i in range(VOL_N, len(cl)):
            w = r[i - VOL_N + 1:i + 1]
            m = sum(w) / VOL_N
            v = math.sqrt(sum((x - m) ** 2 for x in w) / (VOL_N - 1))
            self.vol[i] = v
            if v > 0 and cl[i - VOL_N] > 0:
                self.z[i] = math.log(cl[i] / cl[i - VOL_N]) / (v * math.sqrt(VOL_N))
        for i in range(VOL_N + YEAR_N, len(cl)):
            past = [x for x in self.vol[i - YEAR_N:i] if x is not None]
            if past and self.vol[i] is not None:
                self.pct[i] = sum(1 for x in past if x < self.vol[i]) / len(past)

    def at(self, t: float) -> int | None:
        """Index of the last daily candle that was closed at time t (a daily candle covers [t, t + 1 day))."""
        k = bisect.bisect_right(self.t, t - 86400) - 1
        return k if k >= 0 else None


class Events:
    """High-impact US release times known in advance: the calendar table, and before it the payroll Friday."""

    def __init__(self, db: DB):
        try:
            rows = db.execute("SELECT ts, event, impact FROM releases ORDER BY ts").fetchall()
        except Exception:               # no calendar table yet: the payroll Friday only
            rows = []
        ts = {r["ts"] for r in rows if str(r["impact"] or "").lower() == "high"
              or any(k in str(r["event"] or "").lower() for k in EVENT_RE)}
        try:                            # the past release dates from FRED (CPI, payrolls, GDP, PCE)
            hist = json.loads(db.get("calendar:history") or "{}")
        except ValueError:
            hist = {}
        for v in hist.values():
            ts.update(v)
        self.ts = sorted(ts)
        self.covered_from = self.ts[0] if self.ts else None
        self.sources = sorted(hist)

    def inside(self, t0: float, t1: float) -> bool:
        if self.covered_from is not None and t1 >= self.covered_from:
            k = bisect.bisect_right(self.ts, t0)
            return k < len(self.ts) and self.ts[k] <= t1
        return _payroll_inside(t0, t1)


def _payroll_inside(t0: float, t1: float) -> bool:
    """Before the calendar table: the US jobs report, the first Friday of the month at 08:30 New York."""
    d = datetime.fromtimestamp(t0, NY).date().replace(day=1)
    end = datetime.fromtimestamp(t1, NY).date()
    while d <= end:
        f = d + timedelta(days=(4 - d.weekday()) % 7)
        ts = datetime(f.year, f.month, f.day, 8, 30, tzinfo=NY).timestamp()
        if t0 < ts <= t1:
            return True
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return False


def state(daily: Daily, events: Events, t0: float, t1: float) -> str | None:
    """The market state of a forecast issued at t0 for t1, from what was known at t0 (calendar dates are known ahead)."""
    # a day-or-longer forecast is an «event» one only when the release comes within its first day: otherwise almost
    # every weekly forecast would be one (research review 2026-11-26)
    if events.inside(t0, min(t1, t0 + 86400)):
        return "hadisə"
    i = daily.at(t0)
    if i is None or daily.pct[i] is None:
        return None
    if daily.pct[i] >= SHOCK_PCT:
        return "şok"
    if daily.z[i] is not None and abs(daily.z[i]) >= TREND_Z:
        return "trend"
    return "yan"


# ---------- the evidence ----------
def _ny_day(t: float) -> str:
    return datetime.fromtimestamp(t, NY).strftime("%Y-%m-%d")


def _chi_days(cells: dict) -> float | None:
    """p-value that the voice's hit rate is the same in every state, counting trading days (a day is right when most
    of that day's views were right): a chi-square test on days, so 30 forecasts of one day count once."""
    tab = [(c["day_hits"], c["days"] - c["day_hits"]) for c in cells.values() if c["days"] >= MIN_DAYS]
    if len(tab) < 2:
        return None
    hit = sum(a for a, _ in tab)
    tot = sum(a + b for a, b in tab)
    if hit == 0 or hit == tot:
        return None
    p = hit / tot
    x2 = sum((a - (a + b) * p) ** 2 / ((a + b) * p) + (b - (a + b) * (1 - p)) ** 2 / ((a + b) * (1 - p))
             for a, b in tab)
    return round(_chi2_sf(x2, len(tab) - 1), 4)


def _chi2_sf(x: float, k: int) -> float:
    """Upper tail of the chi-square distribution (k degrees of freedom), via the regularized gamma function."""
    a, z = k / 2.0, x / 2.0
    if z <= 0:
        return 1.0
    if z < a + 1:                       # series for the lower part
        s, term, n = 1.0 / a, 1.0 / a, 1
        while abs(term) > 1e-12 and n < 500:
            term *= z / (a + n)
            s += term
            n += 1
        return max(0.0, 1.0 - s * math.exp(-z + a * math.log(z) - math.lgamma(a)))
    b, c, d = z + 1 - a, 1e300, 1 / (z + 1 - a)     # continued fraction for the upper part
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return min(1.0, math.exp(-z + a * math.log(z) - math.lgamma(a)) * h)


def _desk_rows(db: DB, symbol: str, horizon: str) -> list:
    live0 = db.execute("SELECT MIN(issued_t) t FROM forecasts WHERE symbol=? AND horizon=? AND mode='live'",
                       (symbol, horizon)).fetchone()["t"]
    cut = live0 if live0 is not None else 1e18
    return db.execute("SELECT method, issued_t, target_t, p_up, outcome, hit FROM forecasts WHERE symbol=? AND "
                      "horizon=? AND hit IS NOT NULL AND outcome IS NOT NULL AND p_up != 0.5 AND "
                      "((mode='history' AND issued_t < ?) OR mode='live') ORDER BY issued_t DESC LIMIT ?",
                      (symbol, horizon, cut, MAX_ROWS)).fetchall()


def audit_desk(db: DB, symbol: str, horizon: str, daily: Daily, events: Events) -> dict:
    rows = _desk_rows(db, symbol, horizon)
    st_of: dict[tuple, str | None] = {}
    up = {s: [0, 0] for s in STATES}                 # per state: ups, moments (one per moment, not per voice)
    seen_moment: set = set()
    acc: dict[str, dict[str, dict]] = {}
    day_acc: dict[tuple, list] = {}
    for r in rows:
        m = r["method"]
        if not _voice(m):
            continue
        key = (r["issued_t"], r["target_t"])
        if key not in st_of:
            st_of[key] = state(daily, events, r["issued_t"], r["target_t"])
        s = st_of[key]
        if s is None:
            continue
        if key not in seen_moment:
            seen_moment.add(key)
            up[s][0] += int(r["outcome"])
            up[s][1] += 1
        c = acc.setdefault(m, {}).setdefault(s, {"n": 0, "hits": 0})
        c["n"] += 1
        c["hits"] += int(r["hit"])
        d = day_acc.setdefault((m, s, _ny_day(r["issued_t"])), [0, 0])
        d[0] += int(r["hit"])
        d[1] += 1
    for (m, s, _), (h, n) in day_acc.items():
        c = acc[m][s]
        c["days"] = c.get("days", 0) + 1
        c["day_hits"] = c.get("day_hits", 0) + (1 if 2 * h > n else 0)
    bars = {s: (max(0.5, u / n, 1 - u / n) if n else None) for s, (u, n) in up.items()}
    voices = {}
    for m, cells in acc.items():
        out = {}
        for s, c in cells.items():
            c.setdefault("days", 0)
            c.setdefault("day_hits", 0)
            hr = c["hits"] / c["n"] if c["n"] else None
            out[s] = {"n": c["n"], "days": c["days"], "hit_rate": None if hr is None else round(hr, 4),
                      "edge": None if hr is None or bars[s] is None else round(hr - bars[s], 4),
                      "readable": c["days"] >= MIN_DAYS, "day_hits": c["day_hits"]}
        voices[m] = {"states": out, "p_same": _chi_days(cells)}
    best = {}
    for s in STATES:
        cand = [(v["states"][s]["edge"], m) for m, v in voices.items()
                if s in v["states"] and v["states"][s]["readable"] and v["states"][s]["edge"] is not None]
        if cand:
            e, m = max(cand)
            best[s] = {"voice": m, "edge": e}
    return {"moments": {s: n for s, (_, n) in up.items()}, "bars": {s: None if b is None else round(b, 4)
                                                                     for s, b in bars.items()},
            "voices": voices, "best": best, "rows": len(rows)}


def audit(db: DB, symbols: tuple[str, ...] = ("XAU", "XAG", "XPT", "XPD")) -> dict:
    from . import candles
    t0 = time.time()
    events = Events(db)
    out: dict = {"computed": None, "ver": VER, "states": list(STATES), "events_from": events.covered_from,
                 "event_sources": getattr(events, "sources", []), "desks": {}}
    for s in symbols:
        daily = Daily(candles.get(db, s, "1d", limit=4000))
        for h in AUDIT_HORIZONS:
            try:
                out["desks"][f"{s}:{h}"] = audit_desk(db, s, h, daily, events)
            except Exception as e:          # one desk failing never stops the others
                out["desks"][f"{s}:{h}"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    out["computed"] = time.time()
    out["seconds"] = round(time.time() - t0, 1)
    db.put(AUDIT_KEY, json.dumps(out, ensure_ascii=False))
    return out


def audit_due(db: DB, now: float | None = None) -> bool:
    raw = db.get(AUDIT_KEY)
    if not raw:
        return True
    try:
        a = json.loads(raw)
        if not a.get("event_sources") and db.get("calendar:history"):    # the past release dates have just arrived
            return True
        return a.get("ver") != VER or (time.time() if now is None else now) - (a.get("computed") or 0) > 86400
    except ValueError:
        return True


def audit_view(db: DB) -> dict | None:
    """The stored evidence, short: per desk the moments per state, the best voice per state and the voices whose hit
    rate differs between states (p < 0.05 on trading days)."""
    raw = db.get(AUDIT_KEY)
    if not raw:
        return None
    try:
        a = json.loads(raw)
    except ValueError:
        return None
    desks = {}
    for k, d in a.get("desks", {}).items():
        if "error" in d:
            desks[k] = d
            continue
        differ = sorted((v["p_same"], m) for m, v in d["voices"].items() if v["p_same"] is not None and
                        v["p_same"] < 0.05)
        desks[k] = {"moments": d["moments"], "bars": d["bars"], "best": d["best"],
                    "differ": [{"voice": m, "p": p} for p, m in differ],
                    "tested": sum(1 for v in d["voices"].values() if v["p_same"] is not None)}
    return {"computed": a.get("computed"), "seconds": a.get("seconds"), "events_from": a.get("events_from"),
            "event_sources": a.get("event_sources"),
            "desks": desks}


# ---------- part 2: the conductor itself, in the shadow ----------
# How it combines (from the research, 2026-11-26): only the voices that have a view at a moment take part and only they
# learn from it («specialists» / sleeping experts, Freund et al. 1997); weights fall with each voice's Brier loss
# (exponential weights) and a small share returns to everyone each round (Fixed Share, Herbster & Warmuth 1998), so a
# voice that is weak now can come back; each market state keeps its own weights, pulled towards the overall weights
# until the state has its own record (shrinkage: few states, little data per state — the combination puzzle says
# estimated weights lose to equal weights when data is short). It is compared, walk-forward and out of sample, with the
# plain average of the same voices (the benchmark) and with the same weights without states. Nothing here reaches a
# live forecast: the owner decides, on this evidence, whether it ever does.
ETA_C = 2.0                  # learning rate on the Brier loss (0..1)
ALPHA = 0.005                # Fixed Share: the share of weight returned to all voices each round
SHRINK_N = 100               # a state's own weights reach half weight after this many separate trading days in it
ABSTAIN = 0.02               # |p - 0.5| below this: «bilmirəm» (no direction), fixed in advance; also below the cost
                             # break-even 0.5 + cost / (2 x average move), whichever is larger
SIM_MOMENTS = 6000
SIM_KEY = "conductor:shadow"
ARMS = ("orta", "ümumi", "dirijor")     # plain average, weights without states, weights per state


class _Weights:
    def __init__(self):
        self.logw: dict[str, float] = {}

    def p(self, views: dict[str, float]) -> float | None:
        if not views:
            return None
        lw = {m: self.logw.get(m, 0.0) for m in views}
        top = max(lw.values())
        w = {m: math.exp(v - top) for m, v in lw.items()}
        s = sum(w.values())
        return sum(w[m] * views[m] for m in views) / s

    def rel(self, views) -> dict[str, float]:
        lw = {m: self.logw.get(m, 0.0) for m in views}
        if not lw:
            return {}
        top = max(lw.values())
        w = {m: math.exp(v - top) for m, v in lw.items()}
        s = sum(w.values())
        return {m: v / s for m, v in w.items()}

    def learn(self, views: dict[str, float], y: float) -> None:
        for m, p in views.items():                      # only the awake voices learn
            self.logw[m] = self.logw.get(m, 0.0) - ETA_C * (p - y) ** 2
        if self.logw:                                    # Fixed Share: a little weight goes back to everyone
            top = max(self.logw.values())
            w = {m: math.exp(v - top) for m, v in self.logw.items()}
            mean = sum(w.values()) / len(w)
            self.logw = {m: math.log((1 - ALPHA) * v + ALPHA * mean) for m, v in w.items()}


def _moments(db: DB, symbol: str, horizon: str) -> list[dict]:
    live0 = db.execute("SELECT MIN(issued_t) t FROM forecasts WHERE symbol=? AND horizon=? AND mode='live'",
                       (symbol, horizon)).fetchone()["t"]
    cut = live0 if live0 is not None else 1e18
    t0 = db.execute("SELECT MIN(issued_t) t FROM (SELECT DISTINCT issued_t FROM forecasts WHERE symbol=? AND horizon=? "
                    "AND price1 IS NOT NULL AND ((mode='history' AND issued_t < ?) OR mode='live') "
                    "ORDER BY issued_t DESC LIMIT ?)", (symbol, horizon, cut, SIM_MOMENTS)).fetchone()["t"]
    if t0 is None:
        return []
    rows = db.execute("SELECT issued_t, target_t, method, p_up, price0, price1 FROM forecasts WHERE symbol=? AND "
                      "horizon=? AND issued_t >= ? AND price1 IS NOT NULL AND ((mode='history' AND issued_t < ?) OR "
                      "mode='live')", (symbol, horizon, t0, cut)).fetchall()
    mom: dict[int, dict] = {}
    for r in rows:
        m = mom.setdefault(r["issued_t"], {"t": r["issued_t"], "target": r["target_t"], "p0": r["price0"],
                                           "p1": r["price1"], "v": {}})
        if _voice(r["method"]) and r["p_up"] is not None and r["p_up"] != 0.5:
            m["v"][r["method"]] = min(0.95, max(0.05, float(r["p_up"])))
    return sorted((m for m in mom.values() if m["v"] and m["p1"] != m["p0"]), key=lambda m: m["t"])


def _ci(xs: list[float]) -> tuple[float, float, float] | None:
    if len(xs) < 10:
        return None
    n = len(xs)
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
    half = 1.96 * sd / math.sqrt(n)
    return round(mu, 5), round(mu - half, 5), round(mu + half, 5)


def _blocks(xs: list[float], k: int) -> list[float]:
    """Means of consecutive blocks of k days: forecasts whose horizons overlap are not independent day to day."""
    if k <= 1:
        return xs
    return [sum(xs[i:i + k]) / len(xs[i:i + k]) for i in range(0, len(xs), k)]


def simulate(seq: list[dict], states: list[str | None], cost: float, block_days: int = 1) -> dict:
    """Walk-forward: at each moment the three arms predict first (only outcomes already known are learned), then the
    moment waits for its outcome. Scores per arm, and per trading day the Brier difference against the plain average."""
    g = _Weights()
    per: dict[str, _Weights] = {s: _Weights() for s in STATES}
    seen = {s: 0 for s in STATES}            # separate trading days with a resolved moment, per state
    seen_day: dict[str, set] = {s: set() for s in STATES}
    moves = [0.0, 0]                         # running average |return| of resolved moments (for the cost break-even)
    pending: list[tuple[dict, str | None]] = []
    sc = {a: {"n": 0, "viewed": 0, "hits": 0, "brier": 0.0, "net": 0.0, "ups": 0} for a in ARMS}
    by_day: dict[str, dict[str, list]] = {}
    hist: list[tuple[float, dict]] = []                  # (t, relative state weights) for the «woke up» check
    for m, s in zip(seq, states):
        still = []
        for q, qs in pending:
            if q["target"] <= m["t"]:
                y = 1.0 if q["p1"] > q["p0"] else 0.0
                g.learn(q["v"], y)
                moves[0] += abs(q["p1"] / q["p0"] - 1)
                moves[1] += 1
                if qs is not None:
                    per[qs].learn(q["v"], y)
                    seen_day[qs].add(_ny_day(q["t"]))
                    seen[qs] = len(seen_day[qs])
            else:
                still.append((q, qs))
        pending = still
        y = 1.0 if m["p1"] > m["p0"] else 0.0
        p_avg = sum(m["v"].values()) / len(m["v"])
        p_g = g.p(m["v"])
        if s is None:
            p_c = p_g
        else:
            lam = SHRINK_N / (SHRINK_N + seen[s])        # little record in this state -> mostly the overall weights
            p_c = (1 - lam) * per[s].p(m["v"]) + lam * p_g
            if len(hist) == 0 or m["t"] - hist[-1][0] > 86400:
                hist.append((m["t"], {k: round(v, 4) for k, v in per[s].rel(m["v"]).items()}))
        day = _ny_day(m["t"])
        dd = by_day.setdefault(day, {a: [] for a in ARMS})
        ret = m["p1"] / m["p0"] - 1
        avg_move = moves[0] / moves[1] if moves[1] else 0.0
        need = max(ABSTAIN, cost / (2 * avg_move)) if avg_move > 0 else ABSTAIN
        for a, p in (("orta", p_avg), ("ümumi", p_g), ("dirijor", p_c)):
            r = sc[a]
            r["n"] += 1
            r["ups"] += int(y)
            r["brier"] += (p - y) ** 2
            dd[a].append((p - y) ** 2)
            if abs(p - 0.5) >= need:
                r["viewed"] += 1
                r["hits"] += int((p > 0.5) == (y == 1.0))
                r["net"] += (ret if p > 0.5 else -ret) - cost
        m["_s"] = s
        pending.append((m, s))
    out = {}
    for a, r in sc.items():
        bar = max(0.5, r["ups"] / r["n"], 1 - r["ups"] / r["n"]) if r["n"] else 0.5
        out[a] = {"n": r["n"], "viewed": r["viewed"], "hit_rate": round(r["hits"] / r["viewed"], 4) if r["viewed"] else None,
                  "bar": round(bar, 4), "bss": round(1 - (r["brier"] / r["n"]) / 0.25, 5) if r["n"] else None,
                  "net_avg": round(r["net"] / r["viewed"], 6) if r["viewed"] else None}
    diffs = {a: [sum(d[a]) / len(d[a]) - sum(d["orta"]) / len(d["orta"]) for d in by_day.values()]
             for a in ("ümumi", "dirijor")}
    vs = {a: _ci(_blocks(x, block_days)) for a, x in diffs.items()}           # negative = lower Brier than the plain average (better)
    return {"arms": out, "vs_orta": {a: (None if c is None else {"mean": c[0], "lo": c[1], "hi": c[2]})
                                     for a, c in vs.items()}, "days": len(by_day), "seen": seen,
            "weights_now": {s: per[s].rel({k: 0 for k in per[s].logw}) for s in STATES}, "hist": hist}


def _woke(hist: list[tuple[float, dict]], back: int = 20) -> list[str]:
    """Voices whose share in their state's weights rose from under 2/3 of an equal share to over 1.5 x within the last
    ~20 days: a muted voice that has come back."""
    if len(hist) <= back:
        return []
    old, new = hist[-back - 1][1], hist[-1][1]
    out = []
    for m, w in new.items():
        eq = 1 / max(1, len(new))
        if w > 1.5 * eq and old.get(m, eq) < eq * 2 / 3:
            out.append(m)
    return sorted(out)


def shadow(db: DB, symbols: tuple[str, ...] = ("XAU", "XAG", "XPT", "XPD")) -> dict:
    from . import candles
    from .judge import full_cost
    t0 = time.time()
    events = Events(db)
    out: dict = {"computed": None, "desks": {}, "params": {"eta": ETA_C, "alpha": ALPHA, "shrink_n": SHRINK_N,
                                                         "abstain": ABSTAIN}}
    for s in symbols:
        daily = Daily(candles.get(db, s, "1d", limit=4000))
        for h in AUDIT_HORIZONS:
            try:
                seq = _moments(db, s, h)
                if not seq:
                    continue
                sts = [state(daily, events, m["t"], m["target"]) for m in seq]
                span = (seq[-1]["target"] - seq[-1]["t"]) / 86400
                r = simulate(seq, sts, full_cost(s, h), block_days=max(1, round(span)))
                now_state = state(daily, events, time.time(), time.time() + (seq[-1]["target"] - seq[-1]["t"]))
                wn = r["weights_now"].get(now_state) or {}
                lead = max(wn.items(), key=lambda kv: kv[1])[0] if wn else None
                out["desks"][f"{s}:{h}"] = {k: r[k] for k in ("arms", "vs_orta", "days", "seen")} | {
                    "state_now": now_state, "leader_now": lead, "woke": _woke(r["hist"]),
                    "top_now": sorted(wn.items(), key=lambda kv: -kv[1])[:3]}
            except Exception as e:          # one desk failing never stops the others
                out["desks"][f"{s}:{h}"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    out["computed"] = time.time()
    out["seconds"] = round(time.time() - t0, 1)
    db.put(SIM_KEY, json.dumps(out, ensure_ascii=False))
    return out


def shadow_view(db: DB) -> dict | None:
    raw = db.get(SIM_KEY)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def run(db: DB) -> dict:
    """The daily job: first the evidence, then the shadow conductor."""
    a = audit(db)
    s = shadow(db)
    from . import shadowtests          # owner's block decisions 1 and 3, measured in the shadow
    x = shadowtests.run(db)
    from . import aci                  # plan step 9: the range correction, tested on the past first
    c = aci.shadow(db)
    from . import autopsy              # plan step 11: once a month, why the forecasts missed
    if autopsy.due(db):
        autopsy.run(db)
    from . import blockaudit           # plan phase E: one sheet per block, every day
    try:
        blockaudit.build(db)
    except Exception:
        pass
    import logging
    from . import judgeplus            # plan step 12: weekly, the Judge checks itself and decayed approvals go back
    if time.time() - float(db.get("judge:weekly_ts") or 0) > 7 * 86400:
        db.put("judge:weekly_ts", str(time.time()))
        try:
            judgeplus.canary(db)
        except Exception:
            logging.getLogger("tst.judge").exception("judge canary failed")
        try:
            judgeplus.demote_check(db)
        except Exception:
            logging.getLogger("tst.judge").exception("demote check failed")
    return {"audit_s": a.get("seconds"), "shadow_s": s.get("seconds"), "experiments_s": x.get("seconds"),
            "aci_s": c.get("seconds")}
