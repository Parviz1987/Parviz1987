"""Səhvin yarılması (owner 2026-11-26, plan step 11, strengthened version): why the forecasts miss, measured — never
guessed by a brain, never changing a live forecast. Six layers:

1. Murphy decomposition per voice (Brier = reliability - resolution + uncertainty): is the problem calibration (fixable
   by re-scaling) or no resolution (the voice has no information)?
2. Slices: the headline forecast's miss rate by market state, New York hour, metal and how many voices agreed —
   compared with its overall miss rate, with a Bonferroni correction (no lucky «finding»).
3. Who misled: in the headline's misses, which voices pointed the wrong way, against how often each was right.
4. Decision vs outcome: a «good decision» is a view taken in a probability band that has been right more often than
   not in the past (known at the time); four boxes: good+right, good+wrong (bad luck), bad+right (luck), bad+wrong.
5. The month's 5 biggest misses: a short card each (state, event, move in volatilities, the voices, the cause).
6. Range drift: does the price leave the 80 % range more often above or below?
Each miss also gets ONE cause from a fixed list, checked in this order (the first that fits): məlumat (data gap),
tanış olmayan (unfamiliar: extreme volatility), təqvim (a scheduled US release and a big move), şok (no release, a very
big move), dalğalılıq (the move 1.5x larger or smaller than the range expected), rejim (a 20-day trend turned within
the horizon), səs-küy (a small move the range expected anyway), model (the rest). The list is frozen; a cause that is
far more frequent than usual becomes a hint for the weekly hypothesis agent — which must still pass the Judge."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime

from .db import DB

HEAD = "vahid"
HORIZONS = ("1h", "4h", "1d", "1w")
CAUSES = ("məlumat", "tanış olmayan", "təqvim", "şok", "dalğalılıq", "rejim", "səs-küy", "model")
WINDOW = 250
KEY = "autopsy:last"
BINS = 10


def murphy(ps: list[float], ys: list[int]) -> dict | None:
    n = len(ps)
    if n < 50:
        return None
    base = sum(ys) / n
    rel = res = 0.0
    for b in range(BINS):
        idx = [i for i, p in enumerate(ps) if min(BINS - 1, int(p * BINS)) == b]
        if not idx:
            continue
        pb = sum(ps[i] for i in idx) / len(idx)
        ob = sum(ys[i] for i in idx) / len(idx)
        rel += len(idx) * (pb - ob) ** 2
        res += len(idx) * (ob - base) ** 2
    rel, res, unc = rel / n, res / n, base * (1 - base)
    return {"n": n, "reliability": round(rel, 5), "resolution": round(res, 5), "uncertainty": round(unc, 5),
            "verdict": ("ayırd etmə gücü yoxdur" if res < 0.002 else
                        "kalibrləmə xətası (düzəldilə bilər)" if rel > res / 2 else "məlumatı var")}


def _sigma(r) -> float | None:
    half = (r["hi80"] - r["lo80"]) / 2
    return half / 1.2816 / r["price0"] if r["price0"] and half > 0 else None


def cause(r, sig: float | None, st: str | None, event: bool, daily, ticks_ok: bool) -> str:
    move = math.log(r["price1"] / r["price0"]) if r["price0"] and r["price1"] else 0.0
    z = abs(move) / sig if sig else 0.0
    if not ticks_ok:
        return "məlumat"
    i = daily.at(r["issued_t"]) if daily else None
    if i is not None and daily.pct[i] is not None and (daily.pct[i] >= 0.98 or daily.pct[i] <= 0.02):
        return "tanış olmayan"
    if event and z > 1.5:
        return "təqvim"
    if not event and z > 2.5:
        return "şok"
    if sig and (z > 1.5 * 1.2816 or z < 1 / 1.5 * 0.3):
        return "dalğalılıq"
    if i is not None and daily.z[i] is not None and abs(daily.z[i]) >= 1 and (move > 0) != (daily.z[i] > 0):
        return "rejim"
    if z < 0.5:
        return "səs-küy"
    return "model"


def _binom_z(k: int, n: int, p: float) -> float:
    return (k - n * p) / math.sqrt(n * p * (1 - p)) if n and 0 < p < 1 else 0.0


def desk(db: DB, symbol: str, horizon: str, daily, events) -> dict:
    from . import conductor
    NY = conductor.NY
    rows = db.execute("SELECT method, issued_t, target_t, p_up, price0, price1, lo80, hi80, hit FROM forecasts "
                      "WHERE symbol=? AND horizon=? AND mode='live' AND price1 IS NOT NULL ORDER BY issued_t DESC "
                      "LIMIT 20000", (symbol, horizon)).fetchall()
    by_t: dict[int, dict] = {}
    for r in rows:
        by_t.setdefault(r["issued_t"], {})[r["method"]] = r
    moments = sorted(by_t)[-WINDOW * 4:]
    heads = [(t, by_t[t]) for t in moments if HEAD in by_t[t] and by_t[t][HEAD]["p_up"] != 0.5]
    heads = heads[-WINDOW:]
    out: dict = {"n": len(heads)}
    if len(heads) < 30:
        return out
    # 1. Murphy per voice
    voices: dict[str, tuple[list, list]] = {}
    for t in moments:
        for m, r in by_t[t].items():
            if m in ("rw", "up", "consensus", "terazi") or r["p_up"] == 0.5:
                continue
            v = voices.setdefault(m, ([], []))
            v[0].append(r["p_up"])
            v[1].append(int(r["price1"] > r["price0"]))
    out["murphy"] = {m: murphy(*v) for m, v in voices.items() if len(v[0]) >= 50}
    # causes, slices, who misled, four boxes, big misses
    miss_all = sum(1 for _, g in heads if not g[HEAD]["hit"]) / len(heads)
    causes = {c: 0 for c in CAUSES}
    slices: dict[str, dict[str, list]] = {"vəziyyət": {}, "saat (NY)": {}, "razılıq": {}}
    misled: dict[str, list] = {}
    boxes = {"yaxşı qərar, düz": 0, "yaxşı qərar, səhv (bədbəxtlik)": 0, "pis qərar, düz (şans)": 0,
             "pis qərar, səhv": 0}
    band_rec: dict[int, list] = {}
    big = []
    above = below = 0
    for t, g in heads:
        h = g[HEAD]
        up = h["p_up"] > 0.5
        y = h["price1"] > h["price0"]
        st = conductor.state(daily, events, t, h["target_t"]) if daily else None
        ev = events.inside(t, min(h["target_t"], t + 86400)) if events else False
        n_ticks = db.execute("SELECT COUNT(*) n FROM ticks WHERE symbol=? AND ts BETWEEN ? AND ?",
                             (symbol, t, h["target_t"])).fetchone()["n"] if horizon in ("1h", "4h") else 1
        rw = g.get("rw")
        sig = _sigma(rw) if rw else None
        hour = datetime.fromtimestamp(t, NY).hour
        others = [r for m, r in g.items() if m not in (HEAD, "rw", "up", "consensus", "terazi") and r["p_up"] != 0.5]
        agree = sum(1 for r in others if (r["p_up"] > 0.5) == up)
        agree_b = "hamısı razı" if others and agree == len(others) else "çoxu razı" if agree * 2 > len(others) else \
            "az razı"
        for name, key in (("vəziyyət", st or "?"), ("saat (NY)", f"{hour:02d}"), ("razılıq", agree_b)):
            s = slices[name].setdefault(key, [0, 0])
            s[0] += int(not h["hit"])
            s[1] += 1
        band = min(9, int(h["p_up"] * 10))
        past = band_rec.get(band, [])
        good = len(past) >= 20 and sum(past) / len(past) > 0.5
        boxes[("yaxşı qərar, " if good else "pis qərar, ") + ("düz" if h["hit"] else
                                                               "səhv (bədbəxtlik)" if good else "səhv")] += 1
        band_rec.setdefault(band, []).append(int(h["hit"]))
        if rw:
            if h["price1"] > rw["hi80"]:
                above += 1
            elif h["price1"] < rw["lo80"]:
                below += 1
        if h["hit"]:
            continue
        c = cause(h, sig, st, ev, daily, n_ticks >= 3)
        causes[c] += 1
        for r in others:
            misled.setdefault(r["method"], [0, 0])[0 if (r["p_up"] > 0.5) == (not y) else 1] += 1
        z = abs(math.log(h["price1"] / h["price0"])) / sig if sig else 0.0
        big.append((z, {"t": t, "cause": c, "state": st, "event": ev, "move_sigma": round(z, 2),
                        "said": "yuxarı" if up else "aşağı", "p": h["p_up"],
                        "voices": {r["method"]: round(r["p_up"], 2) for r in others}}))
    out["miss_rate"] = round(miss_all, 4)
    out["causes"] = causes
    tests = sum(len(v) for v in slices.values())
    out["slices"] = {name: {k: {"miss": round(a / b, 3), "n": b, "z": round(_binom_z(a, b, miss_all), 2),
                                "notable": abs(_binom_z(a, b, miss_all)) > _z_bonf(tests) and b >= 20}
                            for k, (a, b) in v.items()} for name, v in slices.items()}
    out["misled"] = {m: {"wrong_way_in_misses": w, "right_way_in_misses": rgt} for m, (w, rgt) in misled.items()}
    out["boxes"] = boxes
    out["range_drift"] = {"above": above, "below": below,
                          "verdict": ("yuxarı sürüşür" if above > 2 * max(1, below) and above >= 10 else
                                      "aşağı sürüşür" if below > 2 * max(1, above) and below >= 10 else "balanslı")}
    big.sort(key=lambda x: -x[0])
    out["biggest"] = [b for _, b in big[:5]]
    return out


def _z_bonf(k: int, alpha: float = 0.05) -> float:
    """Two-sided z for alpha / k (Bonferroni), by bisection on the normal tail."""
    target = alpha / max(1, k) / 2
    lo, hi = 0.0, 10.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if 0.5 * math.erfc(mid / math.sqrt(2)) > target:
            lo = mid
        else:
            hi = mid
    return hi


def run(db: DB, symbols=("XAU", "XAG", "XPT", "XPD")) -> dict:
    from . import candles, conductor
    t0 = time.time()
    events = conductor.Events(db)
    out: dict = {"computed": None, "desks": {}, "causes": list(CAUSES)}
    totals = {c: 0 for c in CAUSES}
    for s in symbols:
        daily = conductor.Daily(candles.get(db, s, "1d", limit=4000))
        for h in HORIZONS:
            try:
                d = desk(db, s, h, daily, events)
            except Exception as e:          # one desk failing never stops the others
                d = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
            out["desks"][f"{s}:{h}"] = d
            for c, n in (d.get("causes") or {}).items():
                totals[c] += n
    out["totals"] = totals
    tot = sum(totals.values())
    # a cause far above its share in the previous month: a hint for the weekly hypothesis agent (never a rule)
    prev = json.loads(db.get(KEY) or "{}").get("totals") or {}
    ptot = sum(prev.values())
    hints = []
    if tot >= 40 and ptot >= 40:
        for c in CAUSES:
            p = max(0.02, prev.get(c, 0) / ptot)
            zc = _binom_z(totals[c], tot, p)
            if zc > _z_bonf(len(CAUSES)) and totals[c] >= 20:
                hints.append({"cause": c, "share": round(totals[c] / tot, 3), "before": round(p, 3), "z": round(zc, 2)})
    out["hints"] = hints
    out["computed"] = time.time()
    out["seconds"] = round(time.time() - t0, 1)
    db.put(KEY, json.dumps(out, ensure_ascii=False))
    return out


def due(db: DB, now: float | None = None) -> bool:
    """Monthly — but daily while too few live headline forecasts exist yet (the first months)."""
    try:
        prev = json.loads(db.get(KEY) or "{}")
    except ValueError:
        prev = {}
    last = prev.get("computed") or 0
    enough = sum(1 for d in (prev.get("desks") or {}).values() if (d.get("n") or 0) >= 30) >= 4
    return (time.time() if now is None else now) - last > (30 if enough else 1) * 86400


def view(db: DB) -> dict | None:
    try:
        return json.loads(db.get(KEY) or "null")
    except ValueError:
        return None
