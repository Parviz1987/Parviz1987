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
VOL_N, YEAR_N = 20, 250
SHOCK_PCT, TREND_Z = 0.80, 1.0
MAX_ROWS = 400000                    # newest rows per desk: bounded memory on the 1 GB server
MIN_DAYS = 20                        # a voice/state cell needs at least this many separate trading days to be read
EVENT_RE = ("cpi", "consumer price", "non farm", "nonfarm", "non-farm", "payroll", "fomc", "fed interest rate",
            "interest rate decision", "pce", "gdp")
AUDIT_KEY = "conductor:audit"


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
        self.ts = sorted(r["ts"] for r in rows if str(r["impact"] or "").lower() == "high"
                         or any(k in str(r["event"] or "").lower() for k in EVENT_RE))
        self.covered_from = self.ts[0] if self.ts else None

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
    if events.inside(t0, t1):
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
        if m in SKIP:
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
    out: dict = {"computed": None, "states": list(STATES), "events_from": events.covered_from, "desks": {}}
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
        return (time.time() if now is None else now) - (json.loads(raw).get("computed") or 0) > 86400
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
            "desks": desks}
