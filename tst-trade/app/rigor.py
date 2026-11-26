"""Sübutun dürüstlüyü (owner 2026-11-25, from the Radar Gold design: «an untouched final period looked at once; count
every attempt»).

1. Cəhd sayğacı — every idea the system has ever tried counts: each method on each desk (metal x horizon), each rule
   on each timeframe, each registered hypothesis, also the retired ones (a set that only grows). A proof is shown next
   to how many attempts it was selected from, with the Šidák-adjusted p: p_all = 1 - (1 - p)^N — the chance that the
   best of N attempts looks this good by luck alone.
2. Son sınaq (one look) — a method or rule that reaches «sübut» becomes a FINALIST at that moment. Its final test uses
   only what happened AFTER that moment (data nobody could have looked at while choosing it), once, when enough cases
   exist; the verdict is stored for good and never recomputed. The Judge's «sübut» (and so any AL / SAT) requires a
   passed final test; until then the status is «namizəd» (candidate).
Nothing here makes a forecast; it only decides how much a result may be trusted."""
from __future__ import annotations

import json
import math
import time

from .db import DB

ALPHA = 0.05
RULE_MIN = 100            # rule finals: cases after the finalist moment


def _seen(db: DB) -> set[str]:
    try:
        return set(json.loads(db.get("trials:seen") or "[]"))
    except ValueError:
        return set()


def trials(db: DB) -> int:
    """The number of attempts ever made (it only grows: a retired idea still counts)."""
    from . import candles, forecast, hypotheses, playbook, rules
    seen = _seen(db)
    for m in list(forecast.METHODS) + list(getattr(forecast, "RETIRED", ())):
        for h in forecast.HORIZONS:
            for s in candles.METALS:
                seen.add(f"m:{m}:{h}:{s}")
    for r in playbook.RULES:
        if r["detector"]:
            for tf in rules.TFS:
                seen.add(f"r:{r['id']}:{tf}")
    # plan step 12: the real number of attempts — the weekly agent's ideas and the shadow experiments count too
    try:
        for r in db.execute("SELECT id FROM ideas WHERE rule IS NULL").fetchall():   # with a rule: counted as r:
            seen.add(f"i:{r['id']}")
    except Exception:
        pass
    for x in ("conductor:dirijor", "conductor:ümumi", "shadow:fa_window", "shadow:festival_vol", "aci:shadow"):
        seen.add(f"x:{x}")
    for group in ("HYPOTHESES", "FOCUS", "V_TESTS"):
        for x in getattr(hypotheses, group, []) or []:
            if isinstance(x, dict) and x.get("id"):
                seen.add(f"h:{x['id']}")
    db.put("trials:seen", json.dumps(sorted(seen)))
    return len(seen)


def p_all(p: float | None, n: int) -> float | None:
    """Šidák: the chance that at least one of n independent tries reaches p by luck."""
    if p is None:
        return None
    return 1 - (1 - min(max(p, 0.0), 1.0)) ** max(1, n)


# ---------- the one-look final test ----------
def _key(kind: str, sym: str, h: str, name: str) -> str:
    return f"final:{kind}:{sym}:{h}:{name}"


def _money_test(rets: list[float], cost: float, k: int) -> tuple[float | None, float | None]:
    """Mean result after cost and the one-sided p (overlap-corrected: n / k independent cases), as the Judge does."""
    n = len(rets)
    if n < 2:
        return None, None
    mean = sum(rets) / n
    var = max(sum((x - mean) ** 2 for x in rets) / (n - 1), 1e-18)
    t = (mean - cost) / math.sqrt(var / max(1.0, n / k))
    return mean - cost, 1 - 0.5 * (1 + math.erf(t / math.sqrt(2)))


def method_final(db: DB, sym: str, horizon: str, method: str, now: float | None = None) -> dict:
    """The final state of a proven method on a desk: registers the finalist moment the first time, then tests once."""
    from .forecast import steps_of
    from .judge import MIN_N, full_cost
    now = time.time() if now is None else now
    key = _key("m", sym, horizon, method)
    st = json.loads(db.get(key) or "null")
    if st is None:
        st = {"since": now, "status": "namizəd"}
        db.put(key, json.dumps(st))
    if st["status"] in ("keçdi", "keçmədi", "insan yoxlaması"):
        return st                                  # looked at once: never again (a possible leak waits for a person)
    rows = db.execute("SELECT issued_t, p_up, price0, price1 FROM forecasts WHERE symbol=? AND horizon=? AND method=? "
                      "AND mode='live' AND issued_t > ? AND price1 IS NOT NULL AND p_up != 0.5 ORDER BY issued_t",
                      (sym, horizon, method, st["since"])).fetchall()
    need = MIN_N.get(horizon, 100)
    st["n"], st["need"] = len(rows), need
    if len(rows) < need:
        db.put(key, json.dumps(st))
        return st
    rows = [r for r in rows if r["price0"]]
    rets = [(r["price1"] / r["price0"] - 1) * (1 if r["p_up"] > 0.5 else -1) for r in rows]
    net, p = _money_test(rets, full_cost(sym, horizon), steps_of(horizon))
    passed = p is not None and p < ALPHA and net > 0
    # plan step 12 (owner 2026-11-26): the strengthened gates, all on the same after-finalist cases, in time order;
    # the bar and the market's base rate come from the cases BEFORE the finalist moment (fixed in advance)
    from . import judgeplus
    from .candles import TF
    from .forecast import HORIZONS
    try:
        cost = full_cost(sym, horizon)
        ys = [int(r["price1"] > r["price0"]) for r in rows]
        hits = [int((r["p_up"] > 0.5) == bool(y)) for r, y in zip(rows, ys)]
        pre = db.execute("SELECT AVG(price1 > price0) u FROM forecasts WHERE symbol=? AND horizon=? AND method='rw' AND "
                         "issued_t <= ? AND price1 IS NOT NULL", (sym, horizon, st["since"])).fetchone()["u"]
        up = pre if pre is not None else 0.5
        srs, matrix = judgeplus.desk_evidence(db, sym, horizon)
        n_trials = trials(db)
        k = steps_of(horizon)
        st["gates"] = judgeplus.gates([x - cost for x in rets], hits, [r["p_up"] for r in rows], ys,
                                      max(0.5, up, 1 - up), k, n_trials, srs, matrix, base_up=up,
                                      times=[r["issued_t"] for r in rows], span=k * TF[HORIZONS[horizon]])
        st["too_good"] = judgeplus.too_good(sum(hits) / len(hits) if hits else None, horizon, max(0.5, up, 1 - up))
        st["trials"], st["data_fp"] = n_trials, judgeplus.fingerprint([tuple(r) for r in rows])
    except Exception as e:             # the gates failing to compute is never a pass; the final waits for the next run
        st["gates_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        db.put(key, json.dumps(st))
        return st
    if st["too_good"]:                 # a possible leak goes to a person, it is not a one-look verdict
        st["status"] = "insan yoxlaması"
        st["card"] = judgeplus.card(st, n_trials)
        db.put(key, json.dumps(st))
        return st
    passed = passed and st["gates"]["ok"]
    if passed:                                      # the independent re-check must agree (R5)
        st["verify"] = verify_method(db, sym, horizon, method, st["since"])
        passed = st["verify"]["ok"]
    st.update({"status": "keçdi" if passed else "keçmədi", "p": p, "net": net, "tested": now})
    st["card"] = judgeplus.card(st, n_trials)
    db.put(key, json.dumps(st))
    log_experiment(db, "final", f"method:{method}:{sym}:{horizon}", st)
    if passed:
        register(db, "method", method, sym, horizon, f"son sınaq: {st['n']} hal, p={p:.4f}")
    return st


def rule_final(db: DB, rule: str, tf: str, now: float | None = None) -> dict:
    """The same for a Bilik kitabı rule (all metals together, net of each metal's cost)."""
    from .judge import full_cost
    now = time.time() if now is None else now
    key = _key("r", "*", tf, rule)
    st = json.loads(db.get(key) or "null")
    if st is None:
        st = {"since": now, "status": "namizəd"}
        db.put(key, json.dumps(st))
    if st["status"] in ("keçdi", "keçmədi"):
        return st
    rows = db.execute("SELECT t, metal, dir, price0, price1 FROM rule_signals WHERE rule=? AND tf=? AND t > ? AND "
                      "price1 IS NOT NULL AND price0 > 0 AND mode != 'futures' ORDER BY t",
                      (rule, tf, st["since"])).fetchall()
    st["n"], st["need"] = len(rows), RULE_MIN
    if len(rows) < RULE_MIN:
        db.put(key, json.dumps(st))
        return st
    nets = [(r["price1"] / r["price0"] - 1) * r["dir"] - full_cost(r["metal"], tf) for r in rows]
    net, p = _money_test(nets, 0.0, 1)
    # plan step 12: t >= 3, the Deflated Sharpe over every attempt ever made, the anytime e-value, not too good —
    # metals firing at the same moment count as ONE case (they are not independent)
    from . import judgeplus
    by_t: dict = {}
    for r, x in zip(rows, nets):
        by_t.setdefault(r["t"], []).append((x, int((r["price1"] - r["price0"]) * r["dir"] > 0)))
    one = [(sum(a for a, _ in v) / len(v), int(sum(h for _, h in v) * 2 > len(v))) for _, v in sorted(by_t.items())]
    hits = [h for _, h in one]
    n_trials = trials(db)
    t = judgeplus.t_stat([a for a, _ in one])
    d = judgeplus.dsr([a for a, _ in one], n_trials)
    e = judgeplus.evalue_hits(hits, 0.5)
    tg = judgeplus.too_good(sum(hits) / len(hits) if hits else None, tf)
    st["gates"] = {"checks": {"t>=3": t is not None and t >= judgeplus.T_MIN,
                              "DSR>=0.95": d is not None and d >= judgeplus.DSR_MIN, "e>=20": e >= judgeplus.E_MIN},
                   "t": t, "dsr": d, "e": round(e, 3)}
    st["gates"]["ok"] = all(st["gates"]["checks"].values())
    st["too_good"], st["trials"] = tg, n_trials
    ok = p is not None and p < ALPHA and net > 0 and st["gates"]["ok"] and not tg
    st.update({"status": "keçdi" if ok else "keçmədi", "p": p, "net": net, "tested": now})
    st["card"] = judgeplus.card(st, n_trials)
    db.put(key, json.dumps(st))
    log_experiment(db, "final", f"rule:{rule}:{tf}", st)
    if st["status"] == "keçdi":
        register(db, "rule", rule, "*", tf, f"son sınaq: {st['n']} hal, p={p:.4f}")
    return st


def finals(db: DB) -> list[dict]:
    """Every finalist and its state (for the pages and the weekly report)."""
    out = []
    for r in db.execute("SELECT k, v FROM kv WHERE k LIKE 'final:%' ORDER BY k").fetchall():
        _, kind, sym, h, name = r["k"].split(":", 4)
        out.append({"kind": "üsul" if kind == "m" else "qayda", "symbol": sym, "horizon": h, "name": name,
                    **json.loads(r["v"])})
    return out


# ---------- independent re-check (Radar Gold R5: «cannot accept its own work») ----------
def verify_method(db: DB, sym: str, horizon: str, method: str, since: float) -> dict:
    """Recompute the final cases a second way, from the candles themselves instead of the stored forecast prices:
    each forecast's start and end close are read again from the candle table and the hit rate counted anew. The
    final passes only when both ways agree (prices within 0.05 %, hit rate within 1 point)."""
    from .candles import TF
    from .forecast import HORIZONS
    step = TF[HORIZONS[horizon]]
    rows = db.execute("SELECT issued_t, target_t, p_up, price0, price1 FROM forecasts WHERE symbol=? AND horizon=? AND "
                      "method=? AND mode='live' AND issued_t > ? AND price1 IS NOT NULL AND p_up != 0.5",
                      (sym, horizon, method, since)).fetchall()
    tf = HORIZONS[horizon]
    closes = {r["t"]: r["c"] for r in db.execute("SELECT t, c FROM candles WHERE symbol=? AND tf=? AND t>=?",
                                                 (sym, tf, since - 2 * step)).fetchall()}
    n = bad = h1 = h2 = 0
    for r in rows:
        a, b = closes.get(r["issued_t"] - step), closes.get(r["target_t"] - step)
        if a is None or b is None:
            continue
        n += 1
        if abs(a / r["price0"] - 1) > 0.0005 or abs(b / r["price1"] - 1) > 0.0005:
            bad += 1
        up = r["p_up"] > 0.5
        h1 += int((r["price1"] > r["price0"]) == up)
        h2 += int((b > a) == up)
    ok = n >= 10 and bad / n < 0.01 and abs(h1 - h2) / n <= 0.01
    return {"n": n, "price_mismatch": bad, "hit_stored": h1 / n if n else None, "hit_recomputed": h2 / n if n else None,
            "ok": ok}


# ---------- strategy registry (Radar Gold: candidate -> final -> owner approval -> versioned registry) ----------
REG_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_registry (kind TEXT, name TEXT, symbol TEXT, horizon TEXT, version TEXT,
  status TEXT, ts REAL, decided_ts REAL, note TEXT, PRIMARY KEY (kind, name, symbol, horizon));
CREATE TABLE IF NOT EXISTS experiments (ts REAL, kind TEXT, name TEXT, version TEXT, data_fp TEXT, result TEXT);
"""


def ensure(db: DB) -> None:
    db.script(REG_SCHEMA)


def version(db: DB) -> str:
    return db.get("app:commit") or "?"


def log_experiment(db: DB, kind: str, name: str, result: dict, data_fp: str = "") -> None:
    """The experiment journal: every final test, re-check and approval with the code version — failed ones too."""
    ensure(db)
    db.execute("INSERT INTO experiments VALUES(?,?,?,?,?,?)", (time.time(), kind, name, version(db), data_fp,
                                                               json.dumps(result, ensure_ascii=False, default=str)[:4000]))


def register(db: DB, kind: str, name: str, sym: str, horizon: str, note: str = "") -> None:
    ensure(db)
    db.execute("INSERT OR IGNORE INTO strategy_registry VALUES(?,?,?,?,?,?,?,?,?)",
               (kind, name, sym, horizon, version(db), "təsdiq gözləyir", time.time(), None, note[:300]))


def registry_status(db: DB, kind: str, name: str, sym: str, horizon: str) -> str | None:
    ensure(db)
    r = db.execute("SELECT status FROM strategy_registry WHERE kind=? AND name=? AND symbol=? AND horizon=?",
                   (kind, name, sym, horizon)).fetchone()
    return r["status"] if r else None


def decide(db: DB, kind: str, name: str, sym: str, horizon: str, approve: bool, note: str = "") -> dict:
    """The owner's decision on a finalist that passed its final test and the re-check."""
    ensure(db)
    st = "təsdiqlənib" if approve else "rədd edilib"
    n = db.execute("UPDATE strategy_registry SET status=?, decided_ts=?, note=? WHERE kind=? AND name=? AND symbol=? "
                   "AND horizon=?", (st, time.time(), note[:300], kind, name, sym, horizon)).rowcount
    if not n:
        raise ValueError("reyestrdə belə namizəd yoxdur")
    log_experiment(db, "decision", f"{kind}:{name}:{sym}:{horizon}", {"status": st, "note": note})
    return {"status": st}


def registry(db: DB) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.execute("SELECT * FROM strategy_registry ORDER BY ts DESC").fetchall()]


def experiments(db: DB, limit: int = 50) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.execute("SELECT * FROM experiments ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()]


# ---------- independent price source (Radar Gold: the result is checked against another price source) ----------
async def price_audit(db: DB, key: str | None) -> dict:
    """Our daily closes (the broker's CFD) against Twelve Data's (an independent source) for the last 30 days: the
    median and the worst gap. A large gap means a forecast may be judged on a wrong price."""
    from .providers.twelvedata import TwelveDataHistory
    if not key:
        return {"ok": False, "msg": "Twelve Data açarı yoxdur"}
    src = TwelveDataHistory(key)
    out = {"ts": time.time(), "metals": {}}
    try:
        for sym in ("XAU", "XAG", "XPT", "XPD"):
            try:
                theirs = {int(t): c for t, o, h, l, c in await src.candles(sym, "1d", 30)}
            except Exception as e:
                out["metals"][sym] = {"error": str(e)[:100]}
                continue
            ours = {r["t"]: r["c"] for r in db.execute("SELECT t, c FROM candles WHERE symbol=? AND tf='1d' AND t>=?",
                                                       (sym, min(theirs or {0: 0}))).fetchall()}
            gaps = sorted(abs(ours[t] / c - 1) for t, c in theirs.items() if t in ours and c)
            out["metals"][sym] = {"days": len(gaps), "median_gap": gaps[len(gaps) // 2] if gaps else None,
                                  "worst_gap": gaps[-1] if gaps else None}
    finally:
        await src.aclose()
    out["ok"] = all((m.get("worst_gap") or 0) < 0.01 for m in out["metals"].values() if "error" not in m)
    db.put("rigor:price_audit", json.dumps(out))
    return out


# ---------- the data a forecast was made from (Radar Gold: snapshot ID) ----------
SNAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS forecast_snap (symbol TEXT, horizon TEXT, issued_t INTEGER, last_t INTEGER, closes_fp TEXT,
  version TEXT, inputs TEXT, PRIMARY KEY (symbol, horizon, issued_t));
"""


def snapshot(db: DB, sym: str, horizon: str, issued_t: int, past: list[dict], fc: dict) -> None:
    """A fingerprint of the candles a live forecast saw and which analysts had a view, with the code version: the
    same forecast can be traced and reproduced later."""
    import hashlib
    db.script(SNAP_SCHEMA)
    tail = ",".join(f"{c['t']}:{c['c']:.4f}" for c in past[-50:])
    fp = hashlib.sha1(tail.encode()).hexdigest()[:16]
    inputs = {m: v["p_up"] for m, v in (fc.get("methods") or {}).items() if v.get("p_up") not in (None, 0.5)}
    db.execute("INSERT OR IGNORE INTO forecast_snap VALUES(?,?,?,?,?,?,?)",
               (sym, horizon, issued_t, past[-1]["t"] if past else None, fp, version(db),
                json.dumps(inputs, separators=(",", ":"))))
