"""Kölgə sınaqları (owner 2026-11-26, block decisions 1 and 3): two changes the research suggested, measured first in
the shadow — nothing here reaches a live forecast; the owner decides on the result.

1. Fundamental weights from the last 3 years only (the 2022 break: gold's link to real yields collapsed while central
   banks bought ~1,000 t a year). The same walk-forward vote as the live «fundamental» voice, with each rule's record
   counted over the whole history (live) or over the last 3 years (shadow); both scored on the same daily moments,
   next-day direction, after the full cost; the daily Brier difference with a 95 % interval.
2. Festival seasons as a volatility flag, not a direction (the 21 days before Diwali and Chinese New Year): is the
   average absolute daily move in those days really larger than on other days, overall and year by year?"""
from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, timedelta, timezone

from .db import DB

KEY = "shadow:experiments"
YEARS3 = 3 * 365 * 86400


def _ci(xs: list[float]) -> dict | None:
    if len(xs) < 30:
        return None
    n = len(xs)
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
    h = 1.96 * sd / math.sqrt(n)
    return {"mean": round(mu, 5), "lo": round(mu - h, 5), "hi": round(mu + h, 5), "n": n}


# ---------- 1. fundamental: whole record vs the last 3 years ----------
def fa_window(db: DB, symbols=("XAU", "XAG", "XPT", "XPD")) -> dict:
    from . import fundamental, rules
    from .judge import full_cost
    live = rules.Lookup(db, prefixes=("FA-",), name="fundamental", tfs=("1d",), families=fundamental.FAMILY)
    win = rules.Lookup(db, prefixes=("FA-",), name="fundamental", tfs=("1d",), families=fundamental.FAMILY,
                       window=YEARS3)
    out = {}
    for s in symbols:
        rows = db.execute("SELECT t, MAX(price0) p0, MAX(price1) p1 FROM rule_signals WHERE metal=? AND tf='1d' AND "
                          "rule LIKE 'FA-%' AND price1 IS NOT NULL AND mode != 'futures' GROUP BY t ORDER BY t",
                          (s,)).fetchall()
        cost = full_cost(s, "1d")
        sc = {"bütün keçmiş": {"n": 0, "viewed": 0, "hits": 0, "brier": 0.0, "net": 0.0},
              "son 3 il": {"n": 0, "viewed": 0, "hits": 0, "brier": 0.0, "net": 0.0}}
        diffs = []
        for r in rows:
            if not r["p0"] or r["p1"] == r["p0"]:
                continue
            t = r["t"] + 86400 + rules.LAG + 1           # the vote is read after the candle has closed
            y = 1.0 if r["p1"] > r["p0"] else 0.0
            ret = r["p1"] / r["p0"] - 1
            ps = {}
            for name, lk in (("bütün keçmiş", live), ("son 3 il", win)):
                p = lk.views(s, t, "1d")["fundamental"][0]
                ps[name] = p
                x = sc[name]
                x["n"] += 1
                x["brier"] += (p - y) ** 2
                if abs(p - 0.5) >= 0.01:
                    x["viewed"] += 1
                    x["hits"] += int((p > 0.5) == (y == 1.0))
                    x["net"] += (ret if p > 0.5 else -ret) - cost
            diffs.append((ps["son 3 il"] - y) ** 2 - (ps["bütün keçmiş"] - y) ** 2)
        out[s] = {k: {"n": v["n"], "viewed": v["viewed"],
                      "hit_rate": round(v["hits"] / v["viewed"], 4) if v["viewed"] else None,
                      "brier": round(v["brier"] / v["n"], 5) if v["n"] else None,
                      "net_avg": round(v["net"] / v["viewed"], 6) if v["viewed"] else None} for k, v in sc.items()}
        out[s]["3il_minus_hamisi_brier"] = _ci(diffs)      # below 0 = the 3-year record forecast better
    return out


# ---------- 2. festivals: a volatility flag ----------
def _festival_days(metal: str) -> set[date]:
    from .slowviews import BEFORE_DAYS, DIWALI, LUNAR_NY
    fests = [(DIWALI, ("XAU", "XAG")), (LUNAR_NY, ("XAU",))]
    out = set()
    for days, metals in fests:
        if metal not in metals:
            continue
        for d in days:
            f = date.fromisoformat(d)
            out.update(f - timedelta(days=k) for k in range(1, BEFORE_DAYS + 1))
    return out


def festival_vol(db: DB, symbols=("XAU", "XAG")) -> dict:
    from . import candles
    out = {}
    for s in symbols:
        cs = candles.get(db, s, "1d", limit=4000)
        flag = _festival_days(s)
        a, b, by_year = [], [], {}
        for i in range(1, len(cs)):
            if cs[i - 1]["c"] <= 0 or cs[i]["c"] <= 0:
                continue
            m = abs(math.log(cs[i]["c"] / cs[i - 1]["c"]))
            d = datetime.fromtimestamp(cs[i]["t"] + candles.SESSION_SHIFT, timezone.utc).date()
            yr = by_year.setdefault(d.year, [[], []])
            (a if d in flag else b).append(m)
            yr[0 if d in flag else 1].append(m)
        if len(a) < 20 or len(b) < 20:
            out[s] = {"note": f"az məlumat ({len(a)} bayram öncəsi gün)"}
            continue
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
        vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
        tstat = (ma - mb) / math.sqrt(va / len(a) + vb / len(b))
        years = [(y, sum(v[0]) / len(v[0]) / (sum(v[1]) / len(v[1]))) for y, v in sorted(by_year.items())
                 if len(v[0]) >= 10 and len(v[1]) >= 50]
        out[s] = {"festival_days": len(a), "other_days": len(b), "ratio": round(ma / mb, 3), "t": round(tstat, 2),
                  "years": len(years), "years_higher": sum(1 for _, r in years if r > 1),
                  "verdict": ("bayram öncəsi dalğalılıq daha yüksəkdir (t > 2)" if tstat > 2 else
                              "fərq sübut olunmayıb" if tstat > -2 else "bayram öncəsi daha sakitdir (t < -2)")}
    return out


# ---------- 3. technical block: the «unfamiliar day» gate (FreqAI-style dissimilarity) ----------
def unfamiliar(db: DB, symbol: str = "XAU", method: str = "qaydalar", horizon: str = "1d") -> dict:
    """Each day is described by 4 numbers known that morning (20-day volatility percentile, 20-day trend in standard
    deviations, the last day's and the last 5 days' move). Its dissimilarity = distance to the nearest of the PAST
    250 days / their average distance to each other. Is the voice's hit rate lower on the most unfamiliar fifth of
    days? If clearly so, a gate that quiets voices on such days is worth a trial (never switched on from here)."""
    from . import candles, conductor
    cs = candles.get(db, symbol, "1d", limit=4000)
    if len(cs) < 400:
        return {"note": "az şam"}
    d = conductor.Daily(cs)
    cl = [c["c"] for c in cs]
    feats = {}
    for i in range(300, len(cs)):
        if d.pct[i] is None or d.z[i] is None or d.vol[i] is None:
            continue
        r1 = math.log(cl[i] / cl[i - 1]) / d.vol[i]
        r5 = math.log(cl[i] / cl[i - 5]) / (d.vol[i] * math.sqrt(5))
        feats[cs[i]["t"]] = (d.pct[i], d.z[i] / 3, r1 / 3, r5 / 3)
    ts = sorted(feats)
    di = {}
    for k in range(250, len(ts)):
        past = [feats[t] for t in ts[k - 250:k]]
        x = feats[ts[k]]
        near = min(math.dist(x, p) for p in past)
        sample = past[::10]
        avg = sum(math.dist(a, b) for a in sample for b in sample) / max(1, len(sample) ** 2 - len(sample))
        di[ts[k]] = near / avg if avg else 0.0
    rows = db.execute("SELECT issued_t, hit FROM forecasts WHERE symbol=? AND horizon=? AND method=? AND hit IS NOT NULL "
                      "AND p_up != 0.5", (symbol, horizon, method)).fetchall()
    pairs = []
    for r in rows:
        k = conductor.Daily.at(d, r["issued_t"])
        if k is not None and cs[k]["t"] in di:
            pairs.append((di[cs[k]["t"]], int(r["hit"])))
    if len(pairs) < 200:
        return {"note": f"az proqnoz ({len(pairs)})"}
    pairs.sort()
    cut = int(len(pairs) * 0.8)
    fam, unf = pairs[:cut], pairs[cut:]
    hf, hu = sum(h for _, h in fam) / len(fam), sum(h for _, h in unf) / len(unf)
    se = math.sqrt(hf * (1 - hf) / len(fam) + hu * (1 - hu) / len(unf))
    z = (hf - hu) / se if se else 0.0
    return {"method": method, "horizon": horizon, "familiar_hit": round(hf, 4), "unfamiliar_hit": round(hu, 4),
            "n_unfamiliar": len(unf), "z": round(z, 2),
            "verdict": "tanış olmayan günlərdə aydın zəifdir (z > 2): darvaza sınağa dəyər" if z > 2 else
                       "fərq sübut olunmayıb: darvaza lazım deyil"}


# ---------- 4. cross-market: which market moves first ----------
def lead_lag(db: DB, symbol: str = "XAU") -> dict:
    """For each related market: does its 1-hour move predict gold's NEXT hour (lead), compared with the same hour
    (together)? Correlation with a t-statistic over the common closed hours."""
    from . import candles
    from .markets import RELATED
    g = {c["t"]: c["c"] for c in candles.get(db, symbol, "1h", limit=6000)}
    gt = sorted(g)
    gr = {gt[i]: math.log(g[gt[i]] / g[gt[i - 1]]) for i in range(1, len(gt)) if gt[i] - gt[i - 1] == 3600}
    out = {}
    for sym in RELATED:
        m = {c["t"]: c["c"] for c in candles.get(db, sym, "1h", limit=6000)}
        mt = sorted(m)
        mr = {mt[i]: math.log(m[mt[i]] / m[mt[i - 1]]) for i in range(1, len(mt)) if mt[i] - mt[i - 1] == 3600
              and m[mt[i - 1]] > 0 and m[mt[i]] > 0}
        lead = [(mr[t], gr[t + 3600]) for t in mr if t + 3600 in gr]
        same = [(mr[t], gr[t]) for t in mr if t in gr]
        if len(lead) < 300:
            out[sym] = {"note": f"az ortaq saat ({len(lead)})"}
            continue
        def corr(xy):
            n = len(xy)
            mx, my = sum(x for x, _ in xy) / n, sum(y for _, y in xy) / n
            sx = math.sqrt(sum((x - mx) ** 2 for x, _ in xy))
            sy = math.sqrt(sum((y - my) ** 2 for _, y in xy))
            r = sum((x - mx) * (y - my) for x, y in xy) / (sx * sy) if sx and sy else 0.0
            return round(r, 4), round(r * math.sqrt(max(1, n - 2) / max(1e-12, 1 - r * r)), 2), n
        rl, tl, nl = corr(lead)
        rs, ts_, ns = corr(same)
        out[sym] = {"lead_r": rl, "lead_t": tl, "same_r": rs, "same_t": ts_, "hours": nl,
                    "verdict": "qızıldan bir saat əvvəl hərəkət edir (|t| > 3)" if abs(tl) > 3 else
                               "öncül deyil (eyni saatda birlikdə hərəkət edə bilər)"}
    return out


def run(db: DB) -> dict:
    t0 = time.time()
    out: dict = {"computed": None}
    for name, fn in (("fa_window", fa_window), ("festival_vol", festival_vol), ("unfamiliar", unfamiliar),
                     ("lead_lag", lead_lag)):
        try:
            out[name] = fn(db)
        except Exception as e:          # one experiment failing never stops the other
            out[name] = {"error": f"{type(e).__name__}: {str(e)[:150]}"}
    out["computed"] = time.time()
    out["seconds"] = round(time.time() - t0, 1)
    db.put(KEY, json.dumps(out, ensure_ascii=False))
    return out


def view(db: DB) -> dict | None:
    try:
        return json.loads(db.get(KEY) or "null")
    except ValueError:
        return None
