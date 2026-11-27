"""Kölgə sınaqları (owner 2026-11-26, block decisions 1 and 3): two changes the research suggested, measured first in
the shadow — nothing here reaches a live forecast; the owner decides on the result.

1. Fundamental weights from the last 3 years only (the 2022 break: gold's link to real yields collapsed while central
   banks bought ~1,000 t a year). The same walk-forward vote as the live «fundamental» voice, with each rule's record
   counted over the whole history (live) or over the last 3 years (shadow); both scored on the same daily moments,
   next-day direction, after the full cost; the daily Brier difference with a 95 % interval.
2. Festival seasons as a volatility flag, not a direction (the 21 days before Diwali and Chinese New Year): is the
   average absolute daily move in those days really larger than on other days, overall and year by year?"""
from __future__ import annotations

import bisect
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
    rows = db.execute("SELECT issued_t, hit, mode FROM forecasts WHERE symbol=? AND horizon=? AND method=? AND hit IS NOT "
                      "NULL AND p_up != 0.5 ORDER BY issued_t", (symbol, horizon, method)).fetchall()
    pairs, seen = [], set()
    for r in rows:                     # one case per day (history and live never both)
        k = conductor.Daily.at(d, r["issued_t"])
        if k is not None and cs[k]["t"] in di and cs[k]["t"] not in seen:
            seen.add(cs[k]["t"])
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
    import time as _t
    now = _t.time()                    # closed hours only (the unfinished hour is one noisy sample)
    g = {c["t"]: c["c"] for c in candles.closed(db, symbol, "1h", now, limit=6000) if c["c"] > 0}
    gt = sorted(g)
    gr = {gt[i]: math.log(g[gt[i]] / g[gt[i - 1]]) for i in range(1, len(gt)) if gt[i] - gt[i - 1] == 3600}
    out = {}
    for sym in RELATED:
        m = {c["t"]: c["c"] for c in candles.closed(db, sym, "1h", now, limit=6000) if c["c"] > 0}
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


# ---------- 5. news block: does a big news moment bring bigger moves? (a volatility flag, not a direction) ----------
def _vol_compare(a: list[float], b: list[float], label: str) -> dict:
    if len(a) < 20 or len(b) < 50:
        return {"cases": len(a), "note": f"az məlumat ({len(a)} {label})"}
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    t = (ma - mb) / math.sqrt(va / len(a) + vb / len(b)) if va + vb > 0 else 0.0
    return {"cases": len(a), "others": len(b), "ratio": round(ma / mb, 3) if mb else None, "t": round(t, 2),
            "verdict": ("sonra tərpəniş daha böyükdür (t > 2): dalğalılıq bayrağı üçün namizəd" if t > 2 else
                        "fərq sübut olunmayıb" if t > -2 else "sonra daha sakitdir (t < -2)")}


def news_shock_vol(db: DB, symbols=("XAU", "XAG", "XPT", "XPD")) -> dict:
    """NW-SHOCK-1 as a flag: the hour after a strength-3 headline about a metal, against the same hour of the day on
    other days (the hour's own rhythm is taken out). Only the headline's arrival time is used."""
    from . import candles
    out = {}
    for s in symbols:
        try:
            ts = [r["ts"] for r in db.execute("SELECT n.ts FROM news n JOIN news_ai a ON a.uid=n.uid WHERE a.strength=3 "
                                              "AND (',' || a.metals || ',') LIKE ?", (f"%,{s},%",)).fetchall()]
        except Exception:
            ts = []
        cs = candles.get(db, s, "1h", limit=4500)
        if not cs:
            out[s] = {"note": "şam yoxdur"}
            continue
        starts = [c["t"] for c in cs]
        flagged = set()
        for t in ts:
            k = bisect.bisect_right(starts, t)       # the first hour that starts after the headline
            if k < len(cs):
                flagged.add(k)
        a, b = [], []
        hour_of = {}
        for i in range(1, len(cs)):
            if cs[i - 1]["c"] <= 0 or cs[i]["c"] <= 0:
                continue
            m = abs(math.log(cs[i]["c"] / cs[i - 1]["c"]))
            hour_of.setdefault(int(cs[i]["t"] // 3600 % 24), []).append((i in flagged, m))
        for rows in hour_of.values():         # each flagged hour against the unflagged same hour of day
            base = [m for f, m in rows if not f]
            mb = sum(base) / len(base) if base else 0
            for f, m in rows:
                if mb > 0:
                    (a if f else b).append(m / mb)
        out[s] = _vol_compare(a, b, "böyük xəbər saatı")
    return out


def geo_shock_vol(db: DB, symbols=("XAU", "XAG", "XPT", "XPD")) -> dict:
    """The library's geopolitical days (GDELT jump): the next trading day's move against all other days."""
    from . import candles, eventlib
    days, vals = eventlib._geo_series(db)
    shock = set()
    for i, d in enumerate(days):
        j = eventlib.geo_jump(vals, i)
        if j is not None and j >= eventlib.GEO_CATS["orta"]:
            shock.add(datetime.fromisoformat(d).date())
    out = {"shock_days": len(shock), "covered_days": len(days)}
    for s in symbols:
        cs = candles.get(db, s, "1d", limit=4000)
        a, b = [], []
        for i in range(1, len(cs)):
            if cs[i - 1]["c"] <= 0 or cs[i]["c"] <= 0:
                continue
            d = datetime.fromtimestamp(cs[i]["t"] + candles.SESSION_SHIFT, timezone.utc).date()
            if days and not (days[0] <= d.isoformat() <= days[-1]):
                continue
            prev = d - timedelta(days=1 if d.weekday() else 3)       # the shock day before this trading day
            m = abs(math.log(cs[i]["c"] / cs[i - 1]["c"]))
            (a if prev in shock else b).append(m)
        out[s] = _vol_compare(a, b, "gərginlik günündən sonrakı gün")
    return out


def run(db: DB) -> dict:
    t0 = time.time()
    out: dict = {"computed": None}
    for name, fn in (("fa_window", fa_window), ("festival_vol", festival_vol), ("unfamiliar", unfamiliar),
                     ("lead_lag", lead_lag), ("news_shock_vol", news_shock_vol), ("geo_shock_vol", geo_shock_vol)):
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
