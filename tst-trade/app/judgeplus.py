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
SR_VAR_FLOOR = 0.5           # the variance of the attempts' (per-case) Sharpe ratios is never counted below this x SR²
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


def dsr(rets: list[float], n_trials: int, trial_srs: list[float] | None = None) -> float | None:
    """Deflated Sharpe Ratio: the probability that the true Sharpe is above what the best of n_trials would show by
    luck. Per-case Sharpe, skew and kurtosis of the returns; the trials' Sharpe variance floored (SR_VAR_FLOOR)."""
    n = len(rets)
    if n < 30:
        return None
    mu = sum(rets) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / (n - 1)) or 1e-12
    sr = mu / sd
    g3 = sum(((x - mu) / sd) ** 3 for x in rets) / n
    g4 = sum(((x - mu) / sd) ** 4 for x in rets) / n
    v = 0.0
    if trial_srs and len(trial_srs) > 1:
        m = sum(trial_srs) / len(trial_srs)
        v = sum((x - m) ** 2 for x in trial_srs) / (len(trial_srs) - 1)
    v = max(v, SR_VAR_FLOOR * sr * sr, 1.0 / n)          # near-duplicate trials cannot shrink the bar
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
        best = max(names, key=lambda k: perf(k, [cuts[i] for i in ins]))
        o = sorted(names, key=lambda k: perf(k, [cuts[i] for i in oos]))
        rank = (o.index(best) + 1) / (len(names) + 1)
        below += int(rank < 0.5)
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


def evalue_hits(hits: list[int], bar: float, lam: float = 0.2, k: int = 1) -> float:
    """Anytime-valid betting e-value for «hit rate > bar»: wealth multiplies by 1 + lam*(hit - bar) case by case
    (every k-th case only, so overlapping horizons are not counted twice). Valid whenever it is looked at."""
    w = 1.0
    for i, h in enumerate(hits):
        if i % max(1, k) == 0:
            w *= 1 + lam * (h - bar)
    return w


def fingerprint(rows) -> str:
    return hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()[:16]


def gates(rets: list[float], hits: list[int], ps: list[float], ys: list[int], bar: float, k: int, n_trials: int,
          trial_srs: list[float], matrix: dict[str, list[float]] | None) -> dict:
    """All the strengthened checks on one finalist's after-finalist cases. ok only when every one holds."""
    t = t_stat(rets, k)
    d = dsr(rets, n_trials, trial_srs)
    p_bo = pbo(matrix, purge=max(1, k)) if matrix else None
    dm_mu, dm_p = diebold_mariano([(p - y) ** 2 for p, y in zip(ps, ys)], [0.25] * len(ys), k)
    e = evalue_hits(hits, bar, k=k)
    checks = {"t>=3": t is not None and t >= T_MIN, "DSR>=0.95": d is not None and d >= DSR_MIN,
              "PBO<=0.10": p_bo is None or p_bo <= PBO_MAX,          # unknown without enough variants: not a block
              "DM p<0.05": dm_p is not None and dm_p < 0.05, "e>=20": e >= E_MIN}
    return {"ok": all(checks.values()), "checks": checks, "t": t, "dsr": d, "pbo": p_bo, "dm_p": dm_p, "e": round(e, 3)}


def card(st: dict, n_trials: int) -> str:
    """The owner's verdict card, in plain words."""
    g = st.get("gates") or {}
    if st.get("status") == "keçdi":
        return f"Sübut var: {n_trials} cəhd içində, xərcdən sonra müsbət, bütün yoxlamalar keçdi."
    miss = [k for k, v in (g.get("checks") or {}).items() if not v]
    why = {"t>=3": "nəticə kifayət qədər güclü deyil (t < 3)", "DSR>=0.95": f"{n_trials} cəhd nəzərə alınanda şans "
           f"ola bilər (DSR {round(g.get('dsr') or 0, 2)})", "PBO<=0.10": "keçmişə həddən artıq uyğunlaşıb (PBO)",
           "DM p<0.05": "«fikri yoxdur»dan yaxşı deyil (Diebold–Mariano)", "e>=20": "gündəlik etibarlı test keçmir"}
    if st.get("net") is not None and st["net"] <= 0:
        miss.insert(0, "net")
        why["net"] = "xərc çıxılandan sonra mənfidir"
    return "Sübut kifayət deyil: " + "; ".join(why.get(m, m) for m in miss[:3]) + "." if miss else \
        "Sübut kifayət deyil."


# ---------- the Judge's own check ----------
def canary(db: DB, symbol: str = "XAU", seed: int | None = None) -> dict:
    """20 rules that flip a coin and 1 rule that peeks at the next close, on the real daily candles. Expected: the
    coins almost never pass the money test at t >= 3, and the peeker is caught as too good to be true."""
    from . import candles
    from .judge import full_cost
    cs = candles.get(db, symbol, "1d", limit=2000)
    if len(cs) < 300:
        return {"note": "az şam"}
    rnd = random.Random(seed if seed is not None else int(time.time() // 604800))
    cost = full_cost(symbol, "1d")
    passed = 0
    for _ in range(20):
        rets = [(cs[i + 1]["c"] / cs[i]["c"] - 1) * rnd.choice((1, -1)) - cost for i in range(len(cs) - 1)]
        t = t_stat(rets)
        passed += int(t is not None and t >= T_MIN)
    peek = [(cs[i + 1]["c"] / cs[i]["c"] - 1) * (1 if cs[i + 1]["c"] > cs[i]["c"] else -1) - cost
            for i in range(len(cs) - 1)]
    hit = sum(1 for x in peek if x > -cost) / len(peek)
    caught = too_good(hit, "1d")
    out = {"ts": time.time(), "random_passed": passed, "random_n": 20, "peek_caught": caught,
           "ok": passed <= 1 and caught}
    db.put("judge:canary", json.dumps(out))
    return out


def too_good(hit_rate: float | None, horizon: str) -> bool:
    """A daily-or-longer metal forecast right more than 65 % of the time is far beyond anything published: it is
    treated as a sign of look-ahead (a leak from the future), not as a discovery, until a person has checked it."""
    return hit_rate is not None and hit_rate > (0.65 if horizon in ("1d", "3d", "1w", "10d", "1mo") else 0.70)


# ---------- demotion ----------
def demote_check(db: DB, now: float | None = None) -> list[str]:
    """Approved methods whose live record decays: a CUSUM alarm on the net result per case (drift 0, threshold 4
    standard deviations) AND a negative net over the last 100 cases -> back to the shadow («kölgəyə qaytarıldı»)."""
    from .forecast import steps_of
    from .judge import full_cost
    from .rigor import REG_SCHEMA, log_experiment
    now = time.time() if now is None else now
    db.script(REG_SCHEMA)
    out = []
    for r in db.execute("SELECT kind, name, symbol, horizon, decided_ts FROM strategy_registry WHERE status='təsdiqlənib' "
                        "AND kind='method'").fetchall():
        rows = db.execute("SELECT p_up, price0, price1 FROM forecasts WHERE symbol=? AND horizon=? AND method=? AND "
                          "mode='live' AND issued_t > ? AND price1 IS NOT NULL AND p_up != 0.5 ORDER BY issued_t",
                          (r["symbol"], r["horizon"], r["name"], r["decided_ts"] or 0)).fetchall()
        cost = full_cost(r["symbol"], r["horizon"])
        nets = [(x["price1"] / x["price0"] - 1) * (1 if x["p_up"] > 0.5 else -1) - cost for x in rows if x["price0"]]
        if len(nets) < 100:
            continue
        mu = sum(nets) / len(nets)
        sd = math.sqrt(sum((x - mu) ** 2 for x in nets) / (len(nets) - 1)) or 1e-12
        s = alarm = 0.0
        for x in nets:
            s = min(0.0, s + x / sd)
            alarm = min(alarm, s)
        if alarm < -4 * math.sqrt(max(1, steps_of(r["horizon"]))) and sum(nets[-100:]) < 0:
            db.execute("UPDATE strategy_registry SET status='kölgəyə qaytarıldı', decided_ts=?, note=? WHERE kind=? AND "
                       "name=? AND symbol=? AND horizon=?", (now, f"canlıda zəiflədi (CUSUM {alarm:.1f}, son 100 hal "
                                                                f"net {sum(nets[-100:]):.4f})", r["kind"], r["name"],
                                                            r["symbol"], r["horizon"]))
            log_experiment(db, "demote", f"{r['name']}:{r['symbol']}:{r['horizon']}", {"cusum": alarm})
            out.append(f"{r['name']} {r['symbol']} {r['horizon']}")
    return out


def desk_evidence(db: DB, sym: str, horizon: str, limit: int = 3000) -> tuple[list[float], dict[str, list[float]]]:
    """Every attempt on one desk over its replayed history: each method's per-case Sharpe (for the DSR spread) and its
    net result per common forecast moment (the PBO matrix)."""
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
