"""Hakimin gücləndirilməsi (owner 2026-11-26, plan step 12, the strengthened version; this file is protected).

The final test (app/rigor.py) passes a method only when ALL of these hold, on the cases after it became a finalist:
- money test after the full cost with t >= 3 (Harvey, Liu & Zhu: the bar for a new idea after many tries);
- Deflated Sharpe Ratio >= 0.95 (Bailey & López de Prado): the Sharpe ratio deflated for how many attempts were
  made, with a floor on the spread of the attempts' Sharpe ratios (near-duplicate trials must not lower the bar);
- Probability of Backtest Overfitting <= 0.10 (CSCV, Bailey et al.), with a purge of one horizon between blocks;
- Diebold–Mariano with a Newey–West (HAC) variance, lag = horizon: better than «no view» (p = 0.5) on Brier loss —
  overlapping forecasts are not counted as independent;
- an anytime-valid e-value >= 20 on the hit rate against its bar (a betting test that may be looked at every day).
Besides: a weekly self-check of the Judge (20 random rules must almost never pass; a rule that peeks at the next
candle must be caught as «too good to be true»), and demotion: an approved method whose live result decays (CUSUM
alarm and a negative net over its last 100 cases) goes back to the shadow by itself; going back to live is always the
owner's decision. Every verdict carries the code version, the data fingerprint and the parameters."""
from __future__ import annotations

import hashlib
import json
import math
import random
import time

from .db import DB

DSR_MIN, PBO_MAX, T_MIN, E_MIN = 0.95, 0.10, 3.0, 20.0
# the spread of the attempts' per-case Sharpe ratios is never counted below the sampling noise of one Sharpe ratio
# (1 / n independent cases): near-duplicate attempts cannot shrink the bar — and the floor never depends on the
# candidate itself (review 2026-11-26: a floor proportional to its own Sharpe made any proof impossible)
EULER = 0.5772156649


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _phi_inv(p: float) -> float:
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def t_stat(rets: list[float], k: int = 1) -> float | None:
    n = len(rets)
    if n < 3:
        return None
    mu = sum(rets) / n
    var = sum((x - mu) ** 2 for x in rets) / (n - 1)
    return mu / math.sqrt(max(var, 1e-18) / max(1.0, n / k))


def dsr(rets: list[float], n_trials: int, trial_srs: list[float] | None = None, k: int = 1) -> float | None:
    """Deflated Sharpe Ratio: the probability that the true Sharpe is above what the best of n_trials would show by
    luck. Per-case Sharpe, skew and kurtosis; n counted as n / k independent cases (overlapping horizons); the
    trials' Sharpe variance floored at 1 / n_eff."""
    n_raw = len(rets)
    n = n_raw / max(1, k)
    if n < 30:
        return None
    mu = sum(rets) / n_raw
    sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / (n_raw - 1)) or 1e-12
    sr = mu / sd
    g3 = sum(((x - mu) / sd) ** 3 for x in rets) / n_raw
    g4 = sum(((x - mu) / sd) ** 4 for x in rets) / n_raw
    v = 0.0
    if trial_srs and len(trial_srs) > 1:
        m = sum(trial_srs) / len(trial_srs)
        v = sum((x - m) ** 2 for x in trial_srs) / (len(trial_srs) - 1)
    v = max(v, 1.0 / n)                                  # the floor: the noise of one Sharpe ratio, never the candidate
    nt = max(2, n_trials)
    sr0 = math.sqrt(v) * ((1 - EULER) * _phi_inv(1 - 1 / nt) + EULER * _phi_inv(1 - 1 / (nt * math.e)))
    den = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr * sr))
    return _phi((sr - sr0) * math.sqrt(n - 1) / den)


def pbo(matrix: dict[str, list[float]], blocks: int = 8, purge: int = 1) -> float | None:
    """Probability of Backtest Overfitting by combinatorially symmetric cross-validation: the case sequence is cut
    into `blocks`; for each half/half split the best variant in-sample is ranked out-of-sample; PBO is the share of
    splits where it falls below the median. `purge` cases are dropped at each block edge (overlapping horizons)."""
    from itertools import combinations
    names = [k for k, v in matrix.items() if v]
    if len(names) < 2:
        return None
    n = min(len(matrix[k]) for k in names)
    if n < blocks * 10:
        return None
    size = n // blocks
    cuts = [(i * size + purge, (i + 1) * size - purge) for i in range(blocks)]
    def perf(name, idx):
        xs = [x for a, b in idx for x in matrix[name][a:b]]
        if len(xs) < 2:
            return 0.0
        mu = sum(xs) / len(xs)
        sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) or 1e-12
        return mu / sd
    below = total = 0
    for ins in combinations(range(blocks), blocks // 2):
        oos = [i for i in range(blocks) if i not in ins]
        best = max(sorted(names), key=lambda k: perf(k, [cuts[i] for i in ins]))
        o = sorted(sorted(names), key=lambda k: perf(k, [cuts[i] for i in oos]))
        rank = (o.index(best) + 1) / (len(names) + 1)
        below += int(rank <= 0.5)                       # at or below the median out of sample: overfit
        total += 1
    return below / total if total else None


def diebold_mariano(loss_a: list[float], loss_b: list[float], lag: int) -> tuple[float | None, float | None]:
    """d = loss_a - loss_b; HAC (Newey–West, Bartlett weights) variance with `lag`; returns (mean d, one-sided p that
    a is better, i.e. mean d < 0)."""
    d = [a - b for a, b in zip(loss_a, loss_b)]
    n = len(d)
    if n < 30:
        return None, None
    mu = sum(d) / n
    g0 = sum((x - mu) ** 2 for x in d) / n
    s = g0
    for k in range(1, min(lag, n - 1) + 1):
        gk = sum((d[i] - mu) * (d[i - k] - mu) for i in range(k, n)) / n
        s += 2 * (1 - k / (lag + 1)) * gk
    se = math.sqrt(max(s, 1e-18) / n)
    return mu, _phi(mu / se)


LAMS = (0.05, 0.1, 0.2, 0.3)


def evalue_hits(hits: list[int], bar: float, k: int = 1) -> float:
    """Anytime-valid betting e-value for «hit rate > bar» (bar fixed BEFORE these cases): the average wealth of four
    fixed bets (a mixture of test martingales is one too), each multiplying by 1 + lam*(hit - bar). `hits` must be
    the time-thinned, independent cases (the caller thins by time); k is kept for old callers."""
    ws = [1.0] * len(LAMS)
    for h in hits:
        ws = [w * (1 + lam * (h - bar)) for w, lam in zip(ws, LAMS)]
    return sum(ws) / len(ws)


def fingerprint(rows) -> str:
    return hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()[:16]


def thin(times: list[float], span: float) -> list[int]:
    """Indexes of cases at least `span` seconds apart (in time order): independent outcomes for overlapping horizons."""
    out, last = [], -1e18
    for i, t in enumerate(times):
        if t - last >= span:
            out.append(i)
            last = t
    return out


def gates(rets: list[float], hits: list[int], ps: list[float], ys: list[int], bar: float, k: int, n_trials: int,
          trial_srs: list[float], matrix: dict[str, list[float]] | None, base_up: float = 0.5,
          times: list[float] | None = None, span: float = 0.0) -> dict:
    """All the strengthened checks on one finalist's after-finalist cases (in time order). ok only when every one
    holds. bar and base_up come from the cases BEFORE the finalist moment (fixed in advance)."""
    t = t_stat(rets, k)
    d = dsr(rets, n_trials, trial_srs, k)
    p_bo = pbo(matrix, purge=max(1, k)) if matrix else None
    # against the market's own base rate (climatology), not 0.5: «always up» in an up year is no skill
    dm_mu, dm_p = diebold_mariano([(p - y) ** 2 for p, y in zip(ps, ys)], [(base_up - y) ** 2 for y in ys], k)
    idx = thin(times, span) if times else list(range(0, len(hits), max(1, k)))
    e = evalue_hits([hits[i] for i in idx], bar)
    checks = {"t>=3": t is not None and t >= T_MIN, "DSR>=0.95": d is not None and d >= DSR_MIN,
              "PBO<=0.10": p_bo is None or p_bo <= PBO_MAX,
              "DM p<0.05": dm_p is not None and dm_p < 0.05, "e>=20": e >= E_MIN}
    return {"ok": all(checks.values()), "checks": checks, "t": t, "dsr": d, "pbo": p_bo,
            "pbo_note": None if p_bo is not None else "PBO ölçülə bilmədi (az variant və ya az ortaq məlumat)",
            "dm_p": dm_p, "e": round(e, 3), "independent": len(idx)}


def card(st: dict, n_trials: int) -> str:
    """The owner's verdict card, in plain words."""
    g = st.get("gates") or {}
    if st.get("status") == "keçdi":
        return f"Sübut var: {n_trials} cəhd içində, xərcdən sonra müsbət, bütün yoxlamalar keçdi."
    if st.get("too_good"):
        return "İnsan yoxlaması lazımdır: nəticə inanılmaz dərəcədə yaxşıdır (gələcəyə baxma ehtimalı)."
    miss = [k for k, v in (g.get("checks") or {}).items() if not v]
    if st.get("verify") and not st["verify"].get("ok"):
        miss.append("verify")
    why = {"t>=3": "nəticə kifayət qədər güclü deyil (t < 3)", "DSR>=0.95": f"{n_trials} cəhd nəzərə alınanda şans "
           f"ola bilər (DSR {round(g.get('dsr') or 0, 2)})", "PBO<=0.10": "keçmişə həddən artıq uyğunlaşıb (PBO)",
           "DM p<0.05": "bazarın öz meylindən yaxşı deyil (Diebold–Mariano)", "e>=20": "gündəlik etibarlı test keçmir",
           "verify": "müstəqil yenidən hesablama razılaşmadı"}
    if st.get("net") is not None and st["net"] <= 0:
        miss.insert(0, "net")
        why["net"] = "xərc çıxılandan sonra mənfidir"
    return "Sübut kifayət deyil: " + "; ".join(why.get(m, m) for m in miss[:3]) + "." if miss else \
        "Sübut kifayət deyil."


# ---------- the Judge's own check ----------
def _rule_gates(cs: list[dict], dirs: list[int], cost: float, n_trials: int) -> tuple[dict, float, bool]:
    ys = [int(cs[i + 1]["c"] > cs[i]["c"]) for i in range(len(dirs))]
    rets = [(cs[i + 1]["c"] / cs[i]["c"] - 1) * d - cost for i, d in enumerate(dirs)]
    hits = [int((d > 0) == bool(y)) for d, y in zip(dirs, ys)]
    half = len(ys) // 2
    up = sum(ys[:half]) / half if half else 0.5          # the bar and base rate from the first half only
    bar = max(0.5, up, 1 - up)
    g = gates(rets[half:], hits[half:], [0.55 if d > 0 else 0.45 for d in dirs[half:]], ys[half:], bar, 1,
              n_trials, [], None, base_up=up)
    hr = sum(hits[half:]) / max(1, len(hits) - half)
    return g, hr, too_good(hr, "1d", bar)


def canary(db: DB, symbol: str = "XAU", seed: int | None = None) -> dict:
    """The Judge's own check on the real daily candles, through the SAME gates the finals use: 20 coin-flip rules
    must (almost) never pass; a rule that peeks at the next close on 30 % of the days, and one that always peeks,
    must both be caught as too good to be true."""
    from . import candles
    from .judge import full_cost
    from .rigor import trials
    cs = candles.get(db, symbol, "1d", limit=2000)
    if len(cs) < 300:
        return {"note": "az şam"}
    rnd = random.Random(seed if seed is not None else int(time.time() // 604800))
    cost = full_cost(symbol, "1d")
    try:
        n_trials = trials(db)
    except Exception:
        n_trials = 1000
    m = len(cs) - 1
    passed, coin_best = 0, 0.0
    ys = [int(cs[i + 1]["c"] > cs[i]["c"]) for i in range(m)]
    half = len(ys) // 2
    up = sum(ys[:half]) / half if half else 0.5
    bar = max(0.5, up, 1 - up)
    for _ in range(20):
        g, hr, _ = _rule_gates(cs, [rnd.choice((1, -1)) for _ in range(m)], cost, n_trials)
        passed += int(g["ok"])
        coin_best = max(coin_best, hr)
    truth = [1 if cs[i + 1]["c"] > cs[i]["c"] else -1 for i in range(m)]
    partial = [t if rnd.random() < 0.3 else rnd.choice((1, -1)) for t in truth]
    _, hr_p, _ = _rule_gates(cs, partial, cost, n_trials)
    _, hr_f, _ = _rule_gates(cs, truth, cost, n_trials)
    # the margin is set here, by the Judge itself: above the luckiest coin, below the 30 % peeker
    lo, hi = coin_best - bar + 0.02, hr_p - bar - 0.005
    new = max(0.10, min(0.15, max(lo, min(0.12, hi))))      # never below 10 points: real edges are not flagged
    margin = round(0.7 * delta(db) + 0.3 * new, 4)            # smoothed over the weeks (one noisy week moves it little)
    db.put(DELTA_KEY, str(margin))
    # the check itself is independent of the margin it set: the 30 % peeker against the plain 12-point margin too
    caught_p = too_good(hr_p, "1d", bar, margin) or too_good(hr_p, "1d", bar, 0.12)
    caught_f = too_good(hr_f, "1d", bar, margin)
    out = {"ts": time.time(), "random_passed": passed, "random_n": 20, "coin_best_hit": round(coin_best, 3),
           "peek30_hit": round(hr_p, 3), "peek30_caught": caught_p, "peek_caught": caught_f, "margin": round(margin, 4),
           "ok": passed <= 1 and caught_p and caught_f}
    db.put("judge:canary", json.dumps(out))
    return out


DELTA_KEY = "judge:too_good_delta"
LONG = ("1d", "3d", "1w", "10d", "1mo")


def delta(db: DB | None) -> float:
    """The «too good» margin for a day or longer, set by the Judge's own weekly check (owner's policy: no person picks
    it): between the best coin-flip rule (+2 points) and a rule that peeks on 30 % of the days (-0.5 point)."""
    try:
        return float(db.get(DELTA_KEY)) if db is not None and db.get(DELTA_KEY) else 0.12
    except (TypeError, ValueError):
        return 0.12


def too_good(hit_rate: float | None, horizon: str, bar: float = 0.5, margin: float | None = None) -> bool:
    """Right far more often than the market's own lean allows (the self-set margin above the bar for a day or longer,
    3 points more for shorter horizons): a possible look-ahead leak, checked automatically (rigor: lag test)."""
    m = 0.12 if margin is None else margin
    return hit_rate is not None and hit_rate > bar + (m if horizon in LONG else m + 0.03)


# ---------- demotion ----------
def _decayed(nets: list[float], k: int) -> tuple[bool, float, float | None]:
    """A one-sided lower CUSUM on the net result per independent case, against the approved level minus a drift of
    half of it, alarm at h = 5 (its CURRENT value, not its lowest ever); AND the last 100 independent cases are
    significantly negative (t < -2). Both together: a real edge on a bad day is not thrown out."""
    xs = nets[::max(1, k)]
    if len(xs) < 120:
        return False, 0.0, None
    ref = max(0.0, sum(xs[:len(xs) // 2]) / (len(xs) // 2))
    mu = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) or 1e-12
    s = 0.0
    for x in xs:
        s = min(0.0, s + (x - (ref - 0.5 * ref)) / sd)
    t = t_stat(xs[-100:])
    return s < -5 and t is not None and t < -2, s, t


def demote_check(db: DB, now: float | None = None) -> list[str]:
    """Approved methods and rules whose live record decayed go back to the shadow («kölgəyə qaytarıldı»); going back
    to live is the owner's decision. Run weekly."""
    from .forecast import steps_of
    from .judge import full_cost
    from .rigor import REG_SCHEMA, log_experiment
    now = time.time() if now is None else now
    db.script(REG_SCHEMA)
    out = []
    for r in db.execute("SELECT kind, name, symbol, horizon, decided_ts FROM strategy_registry WHERE status='təsdiqlənib'"
                        ).fetchall():
        if r["kind"] == "method":
            rows = db.execute("SELECT p_up, price0, price1 FROM forecasts WHERE symbol=? AND horizon=? AND method=? AND "
                              "mode='live' AND issued_t > ? AND price1 IS NOT NULL AND p_up != 0.5 ORDER BY issued_t",
                              (r["symbol"], r["horizon"], r["name"], r["decided_ts"] or 0)).fetchall()
            cost = full_cost(r["symbol"], r["horizon"])
            nets = [(x["price1"] / x["price0"] - 1) * (1 if x["p_up"] > 0.5 else -1) - cost for x in rows if x["price0"]]
            k = steps_of(r["horizon"])
        elif r["kind"] == "rule":
            rows = db.execute("SELECT t, metal, dir, price0, price1 FROM rule_signals WHERE rule=? AND tf=? AND t > ? AND "
                              "price1 IS NOT NULL AND price0 > 0 AND mode != 'futures' ORDER BY t",
                              (r["name"], r["horizon"], r["decided_ts"] or 0)).fetchall()
            by_t: dict = {}
            for x in rows:                     # one case per moment (metals firing together are not independent)
                by_t.setdefault(x["t"], []).append((x["price1"] / x["price0"] - 1) * x["dir"] - full_cost(x["metal"],
                                                                                                         r["horizon"]))
            nets = [sum(v) / len(v) for _, v in sorted(by_t.items())]
            k = 1
        else:
            continue
        bad, s, t = _decayed(nets, k)
        if bad:
            db.execute("UPDATE strategy_registry SET status='kölgəyə qaytarıldı', decided_ts=?, note=? WHERE kind=? AND "
                       "name=? AND symbol=? AND horizon=?", (now, f"canlıda zəiflədi (CUSUM {s:.1f}, son 100 hal "
                                                                f"t={t:.2f})", r["kind"], r["name"], r["symbol"],
                                                            r["horizon"]))
            log_experiment(db, "demote", f"{r['kind']}:{r['name']}:{r['symbol']}:{r['horizon']}", {"cusum": s, "t": t})
            out.append(f"{r['name']} {r['symbol']} {r['horizon']}")
    return out


_EVID: dict = {}


def desk_evidence(db: DB, sym: str, horizon: str, limit: int = 3000) -> tuple[list[float], dict[str, list[float]]]:
    """Every attempt on one desk over its replayed history: each method's per-case Sharpe (for the DSR spread) and its
    net result per common forecast moment (the PBO matrix). Cached per desk for a day (it reads tens of thousands of
    rows)."""
    hit = _EVID.get((sym, horizon))
    if hit and time.time() - hit[0] < 86400:
        return hit[1]
    res = _desk_evidence(db, sym, horizon, limit)
    _EVID[(sym, horizon)] = (time.time(), res)
    return res


def _desk_evidence(db: DB, sym: str, horizon: str, limit: int) -> tuple[list[float], dict[str, list[float]]]:
    from .judge import full_cost
    cost = full_cost(sym, horizon)
    rows = db.execute("SELECT method, issued_t, p_up, price0, price1 FROM forecasts WHERE symbol=? AND horizon=? AND "
                      "mode='history' AND price1 IS NOT NULL AND price0 > 0 ORDER BY issued_t DESC LIMIT ?",
                      (sym, horizon, limit * 20)).fetchall()
    by_m: dict[str, dict[int, float]] = {}
    for r in rows:
        if r["method"] in ("rw", "up") or r["p_up"] == 0.5:
            continue
        by_m.setdefault(r["method"], {})[r["issued_t"]] = (r["price1"] / r["price0"] - 1) * \
            (1 if r["p_up"] > 0.5 else -1) - cost
    srs = []
    for v in by_m.values():
        xs = list(v.values())
        if len(xs) >= 30:
            mu = sum(xs) / len(xs)
            sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) or 1e-12
            srs.append(mu / sd)
    common = None
    for v in by_m.values():
        if len(v) >= 200:
            common = set(v) if common is None else common & set(v)
    matrix = {}
    if common and len(common) >= 80:
        ts = sorted(common)[-limit:]
        matrix = {m: [v[t] for t in ts] for m, v in by_m.items() if all(t in v for t in ts)}
    return srs, matrix
