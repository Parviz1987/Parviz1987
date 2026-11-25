"""Texniki analiz bloku — the page's data (owner 2026-11-25: «one big chart with every tool on it, each switchable; every
rule shown where it fired; per timeframe what the block says and forecasts»).

Everything comes from the block itself (rules.py, patterns.py) and the Judge: the same detectors, the same records,
the same «qaydalar» vote the forecasts use. Nothing is computed differently for the page. Read-only."""
from __future__ import annotations

import json
import time

from . import candles, judge, patterns, playbook, rules
from .db import DB

HORIZON = {"1h": "1h", "4h": "4h", "1d": "1d"}       # the block's timeframe -> the forecast desk it speaks to
LOAD = 520                                           # candles loaded (indicators need ~200 before the visible part)


def _r(v, d=2):
    return None if v is None else round(v, d)


def ichimoku_series(cs: list[dict]) -> dict:
    """Tenkan (9), Kijun (26) and the cloud (spans A/B, drawn 26 candles ahead): values for each candle, past only."""
    n = len(cs)
    mid = lambda a, b: (max(x["h"] for x in cs[a:b]) + min(x["l"] for x in cs[a:b])) / 2
    ten = [mid(i - 8, i + 1) if i >= 8 else None for i in range(n)]
    kij = [mid(i - 25, i + 1) if i >= 25 else None for i in range(n)]
    sb_raw = [mid(i - 51, i + 1) if i >= 51 else None for i in range(n)]
    a = [None] * n
    b = [None] * n
    for i in range(n):
        j = i - 26
        if j >= 0 and ten[j] is not None and kij[j] is not None:
            a[i] = (ten[j] + kij[j]) / 2
        if j >= 0:
            b[i] = sb_raw[j]
    return {"tenkan": ten, "kijun": kij, "a": a, "b": b}


def build(db: DB, sym: str, tf: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    cs = candles.closed(db, sym, tf, now, limit=LOAD)
    out: dict = {"symbol": sym, "tf": tf, "ts": now, "candles": cs}
    if len(cs) < 60:
        out["note"] = "şam azdır"
        return out
    dec = 2 if cs[-1]["c"] >= 100 else 3
    ind = rules.Ind(cs)
    hs, ls = rules._swings(cs, 0, len(cs))
    zz = patterns.zigzag(cs, hs, ls)
    ich = ichimoku_series(cs)
    H = [(j, p) for j, k, p in zz if k == "H"]
    L = [(j, p) for j, k, p in zz if k == "L"]
    tl = []
    if len(L) >= 2 and L[-1][1] > L[-2][1]:
        tl.append({"i0": L[-2][0], "p0": L[-2][1], "i1": L[-1][0], "p1": L[-1][1], "kind": "up"})
    if len(H) >= 2 and H[-1][1] < H[-2][1]:
        tl.append({"i0": H[-2][0], "p0": H[-2][1], "i1": H[-1][0], "p1": H[-1][1], "kind": "down"})
    out["layers"] = {
        "ichimoku": {k: [_r(v, dec) for v in vals] for k, vals in ich.items()},
        "zig": [{"i": j, "p": p, "k": k} for j, k, p in zz[-40:]],
        "tl": tl,
        "stoch": {"k": [_r(v, 1) for v in ind.sk], "d": [_r(v, 1) for v in ind.sd]},
        "adx": {"adx": [_r(v, 1) for v in ind.adx], "pdi": [_r(v, 1) for v in ind.pdi], "mdi": [_r(v, 1) for v in ind.mdi]},
        "vol": [c.get("v") for c in cs],
    }
    # every rule firing on the loaded candles (the same rows the Judge scores)
    idx = {c["t"]: i for i, c in enumerate(cs)}
    fired = []
    for r in db.execute("SELECT t, rule, dir, note FROM rule_signals WHERE metal=? AND tf=? AND t>=? AND mode!='futures' "
                        "AND rule NOT LIKE 'FA-%' AND rule NOT LIKE 'NW-%' ORDER BY t", (sym, tf, cs[0]["t"])).fetchall():
        if r["t"] in idx:
            fired.append({"i": idx[r["t"]], "t": r["t"], "rule": r["rule"], "dir": r["dir"], "note": r["note"]})
    out["fired"] = fired
    # the book: every rule the block detects, its kind, family and the Judge's record on this timeframe
    try:
        rec = json.loads(db.get("ta:records") or "null")
    except ValueError:
        rec = None
    if not rec or now - rec.get("ts", 0) > 900:
        rec = {"ts": now, "r": rules.records(db).get("rules", {})}
        db.put("ta:records", json.dumps(rec, ensure_ascii=False))
    book = []
    for r in playbook.RULES:
        if not r["detector"] or r["area"] not in playbook.TA_AREAS:
            continue
        x = rec["r"].get(r["id"], {}).get(tf)
        book.append({"id": r["id"], "name": r["name"], "area": r["area"], "family": rules.RULE_FAMILY.get(r["id"]),
                     "how": r["how"], "signal": r["signal"], "void": r["void"], "source": r["source"],
                     "record": None if not x else {k: x.get(k) for k in ("n", "hit_rate", "net_avg", "status", "rr",
                                                                           "by_adx")}})
    out["book"] = book
    # what the block says NOW for this timeframe: the rules on the newest candle, one voice per idea, the vote
    last_t = cs[-1]["t"]
    now_rules = [f for f in fired if f["t"] == last_t]
    fam: dict[str, list[int]] = {}
    for f in now_rules:
        fam.setdefault(rules.RULE_FAMILY.get(f["rule"], f["rule"]), []).append(f["dir"])
    fam_lean = {k: (1 if sum(v) > 0 else -1 if sum(v) < 0 else 0) for k, v in fam.items()}
    h = HORIZON[tf]
    p, basis = rules.live_lookup(db).views(sym, now, h)["qaydalar"]
    st = {r["method"]: r for r in judge.stats(db, sym, h, "live", ttl=600)}
    hist = {r["method"]: r for r in judge.stats(db, sym, h, "history", ttl=600)}
    adx_now = ind.adx[-1]
    out["now"] = {
        "t": last_t, "rules": now_rules, "families": fam_lean,
        "up": sum(1 for v in fam_lean.values() if v > 0), "down": sum(1 for v in fam_lean.values() if v < 0),
        "vote": {"p": p, "basis": basis},
        "regime": rules.REGIME_NAMES.get(rules.regime(adx_now)), "adx": _r(adx_now, 1),
        "judge": {m: {"live": {k: (st.get(m) or {}).get(k) for k in ("nh", "hit_rate", "bar", "status")},
                      "history": {k: (hist.get(m) or {}).get(k) for k in ("nh", "hit_rate", "bar", "status")}}
                  for m in ("qaydalar", "chartist")},
        "range": None,
    }
    row = db.execute("SELECT p_up, lo50, hi50, lo80, hi80, price0, issued_t, target_t FROM forecasts WHERE symbol=? "
                     "AND horizon=? AND method='qaydalar' AND mode='live' ORDER BY issued_t DESC LIMIT 1",
                     (sym, h)).fetchone()
    if row:
        out["now"]["range"] = dict(row)
    try:
        ch = json.loads(db.get("chartist:last") or "null")
    except ValueError:
        ch = None
    cm = next((m for m in (ch or {}).get("metals", []) if m.get("symbol") == sym), None)
    if cm:
        out["now"]["chartist"] = {"p": cm.get({"1h": "p1h", "4h": "p4h", "1d": "p1d"}[tf]), "trend": cm.get("trend"),
                                  "levels": cm.get("levels"), "pattern": cm.get("pattern"), "why": cm.get("why"),
                                  "ts": ch.get("ts")}
    return out
