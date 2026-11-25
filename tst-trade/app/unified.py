"""Vahid proqnoz (owner 2026-11-24: «every tool, every brain, every detail must help the forecast; ONE forecast»).

One probability per metal and horizon that the price will be higher at the horizon, learned from the system's own
record, with an honest self-simulation:

- Inputs: every analyst's view on that desk (methods and brains), as x_m = p_up - 0.5 (0 when it has no view).
  Baselines and the other combiners (tərəzi, konsensus, vahid itself) are left out.
- Model: online logistic regression (one weight per analyst + a bias), small steps and a pull towards 0 (L2), so an
  analyst gains weight only by being right, and one lucky streak cannot rule.
- Self-simulation (özünü sınaq), walk-forward in time: the record is replayed forecast by forecast; at each moment the
  model predicts FIRST, using only outcomes that were already known at that moment (target time passed), and only then
  learns from what has become known. So every prediction it is scored on is out-of-sample: the model never saw that
  outcome. The score (hit rate against the bar, Brier skill, net after the full cost) is what the owner sees.
- Data: the history replay before live forecasts began, then the live record (where the brains exist).
- Live: the final weights turn the current views into the unified probability, shrunk towards 0.5 and kept in
  [0.30, 0.70]; the Judge scores it like any analyst (method «vahid»), so its live record builds up honestly.
Recomputed off the event loop every 6 hours (it reads tens of thousands of forecasts per desk)."""
from __future__ import annotations

import json
import math
import time

from .db import DB

SKIP = ("rw", "up", "terazi", "consensus", "vahid")
LR, L2 = 0.08, 0.002
SCALE = 4.0                   # x = (p - 0.5) * SCALE: a 0.6 view is +0.4 before the weight
MAX_MOMENTS = 2500            # newest forecast moments per desk (bounded memory and time)


def _sig(z: float) -> float:
    if z > 30:
        return 1.0
    if z < -30:
        return 0.0
    return 1 / (1 + math.exp(-z))


def _rows(db: DB, symbol: str, horizon: str) -> list:
    live0 = db.execute("SELECT MIN(issued_t) t FROM forecasts WHERE symbol=? AND horizon=? AND mode='live'",
                       (symbol, horizon)).fetchone()["t"]
    cut = live0 if live0 is not None else 1e18
    # the newest MOMENTS (not rows: a moment holds ~35 analysts' rows), so no moment is cut in half
    t0 = db.execute("SELECT MIN(issued_t) t FROM (SELECT DISTINCT issued_t FROM forecasts WHERE symbol=? AND horizon=? "
                    "AND price1 IS NOT NULL AND ((mode='history' AND issued_t < ?) OR mode='live') "
                    "ORDER BY issued_t DESC LIMIT ?)", (symbol, horizon, cut, MAX_MOMENTS)).fetchone()["t"]
    if t0 is None:
        return []
    q = ("SELECT issued_t, target_t, method, p_up, price0, price1 FROM forecasts WHERE symbol=? AND horizon=? "
         "AND issued_t >= ? AND price1 IS NOT NULL AND ((mode='history' AND issued_t < ?) OR mode='live')")
    return db.execute(q, (symbol, horizon, t0, cut)).fetchall()


def simulate(db: DB, symbol: str, horizon: str, rows: list | None = None, exclude: frozenset = frozenset()) -> dict:
    """Walk-forward self-simulation on one desk. Returns the final weights and the out-of-sample score. exclude: the
    analysts left out (the block-value test: the same simulation without one block)."""
    from .judge import full_cost
    rows = _rows(db, symbol, horizon) if rows is None else rows
    # group the analysts' views by forecast moment
    moments: dict[int, dict] = {}
    for r in rows:
        m = moments.setdefault(r["issued_t"], {"t": r["issued_t"], "target": r["target_t"], "p0": r["price0"],
                                               "p1": r["price1"], "x": {}})
        if r["method"] not in SKIP and r["method"] not in exclude and r["p_up"] is not None and r["p_up"] != 0.5:
            m["x"][r["method"]] = (r["p_up"] - 0.5) * SCALE
    seq = sorted(moments.values(), key=lambda m: m["t"])
    w: dict[str, float] = {}
    b = 0.0
    pending: list = []                 # moments predicted but whose outcome is not known yet, by target time
    n = hits = 0
    brier = net = 0.0
    ups = 0
    cost = full_cost(symbol, horizon)
    for m in seq:
        # learn first from every outcome already known at this moment (no look-ahead)
        still = []
        for q in pending:
            if q["target"] <= m["t"]:
                y = 1.0 if q["p1"] > q["p0"] else 0.0
                p = _sig(b + sum(w.get(k, 0.0) * v for k, v in q["x"].items()))
                g = y - p
                b += LR * g * 0.2
                for k, v in q["x"].items():
                    w[k] = w.get(k, 0.0) * (1 - L2) + LR * g * v
            else:
                still.append(q)
        pending = still
        # then predict this moment with what is known
        if m["p1"] != m["p0"]:
            p = _sig(b + sum(w.get(k, 0.0) * v for k, v in m["x"].items()))
            p = 0.5 + 0.5 * (p - 0.5)                         # shrink: the same rule as live
            y = 1.0 if m["p1"] > m["p0"] else 0.0
            ups += int(y)
            n += 1
            brier += (p - y) ** 2
            if abs(p - 0.5) >= 0.01:
                hits += int((p > 0.5) == (y == 1.0))
                ret = m["p1"] / m["p0"] - 1
                net += (ret if p > 0.5 else -ret) - cost
            m["pred"] = p
        pending.append(m)
    viewed = sum(1 for m in seq if "pred" in m and abs(m["pred"] - 0.5) >= 0.01)
    up_rate = ups / n if n else 0.5
    bar = max(0.5, up_rate, 1 - up_rate)
    return {"symbol": symbol, "horizon": horizon, "weights": {k: round(v, 4) for k, v in w.items() if abs(v) > 1e-4},
            "bias": round(b, 4), "n": n, "viewed": viewed, "hit_rate": hits / viewed if viewed else None, "bar": bar,
            "bss": 1 - (brier / n) / 0.25 if n else None, "net_avg": net / viewed if viewed else None,
            "computed": time.time()}


def refresh(db: DB) -> dict:
    from .candles import METALS
    from .forecast import HORIZONS
    out = {}
    for s in METALS:
        for h in HORIZONS:
            try:
                out[f"{s}:{h}"] = simulate(db, s, h)
            except Exception as e:      # one desk failing never stops the others
                out[f"{s}:{h}"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    db.put("unified:models", json.dumps(out, ensure_ascii=False))
    try:
        db.put("unified:ablation", json.dumps(ablation(db), ensure_ascii=False))
    except Exception as e:          # the block-value test never stops the forecasts
        db.put("unified:ablation", json.dumps({"error": f"{type(e).__name__}: {str(e)[:120]}"}))
    return out


ABLATION_DESKS = ("1h", "4h", "1d", "1w")


def ablation(db: DB, symbol: str = "XAU") -> dict:
    """Block value (Radar Gold: «switch a part off and compare»): the unified forecast's walk-forward self-test run
    again without each block's analysts, on the same moments. A block helps if the score drops without it."""
    from .blocks import BLOCKS
    out: dict = {"symbol": symbol, "computed": time.time(), "desks": {}}
    for h in ABLATION_DESKS:
        rows = _rows(db, symbol, h)
        if not rows:
            continue
        full = simulate(db, symbol, h, rows)
        d = {"full": {k: full.get(k) for k in ("viewed", "hit_rate", "bar", "bss", "net_avg")}, "without": {}}
        for b in BLOCKS:
            r = simulate(db, symbol, h, rows, frozenset(b["methods"]))
            d["without"][b["id"]] = {k: r.get(k) for k in ("viewed", "hit_rate", "bss", "net_avg")}
            if full.get("bss") is not None and r.get("bss") is not None:
                d["without"][b["id"]]["bss_change"] = round(r["bss"] - full["bss"], 5)
            if full.get("hit_rate") is not None and r.get("hit_rate") is not None:
                d["without"][b["id"]]["hit_change"] = round(r["hit_rate"] - full["hit_rate"], 5)
        out["desks"][h] = d
    return out


_CACHE: dict = {"ts": 0.0, "models": {}}


def models(db: DB) -> dict:
    if time.time() - _CACHE["ts"] > 300:
        try:
            _CACHE["models"] = json.loads(db.get("unified:models") or "{}")
        except ValueError:
            _CACHE["models"] = {}
        _CACHE["ts"] = time.time()
    return _CACHE["models"]


def view(model: dict | None, out: dict) -> dict:
    """The unified probability from the current views (live only; no model yet -> no view)."""
    if not model or "weights" not in model:
        return {"p_up": 0.5, "basis": "vahid model hələ hesablanmayıb"}
    w = model["weights"]
    z = model.get("bias", 0.0)
    used = []
    for k, v in out.items():
        if k in SKIP or k not in w or not v or v.get("p_up") in (None, 0.5):
            continue
        z += w[k] * (v["p_up"] - 0.5) * SCALE
        used.append(k)
    p = 0.5 + 0.5 * (_sig(z) - 0.5)
    p = round(min(0.70, max(0.30, p)), 4)
    hr = model.get("hit_rate")
    return {"p_up": p if abs(p - 0.5) >= 0.01 else 0.5,
            "basis": f"{len(used)} analitik birləşdi · öz-özünü sınaq: {model.get('viewed', 0)} proqnoz, düz "
                     f"{'—' if hr is None else round(hr * 100)} % (hədd {round(model.get('bar', 0.5) * 100)} %)"}
