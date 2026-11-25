"""Bazarlar arası blok (owner 2026-11-24/25: «every block as deep as the technical one»; 2026-11-25: «why are the
cross-market and time blocks not expanded?»).

How professionals read gold against other markets (intermarket analysis, J. Murphy 1991/2004; WGC GRAM; Baur &
Lucey 2010 and Baur & McDermott 2010 on the safe haven; Erb & Harvey 2013; O'Connor et al. 2015 «The financial
economics of gold»), each idea as a rule of the Bilik kitabı that our code detects on every closed candle (1 h, 4 h,
1 day) and the Judge measures on its own, after costs, like the technical rules:

  dollar      CM-USD-1 the dollar's trend turns (20 candles, scaled by its own volatility)
              CM-USD-2 the dollar jumped and the metal has not followed yet (catch-up, from the old «Dollar impulsu»)
              CM-JPY-1 the yen jumps (USD/JPY falls hard): a safe-haven move
              CM-CNH-1 the yuan weakens: Chinese buyers hedge with gold (only when the broker has USD/CNH)
  rates       CM-YLD-1 the 10-year Treasury's price trend turns (price up = yields down = gold up)
  oil         CM-OIL-1 oil jumped and the metal has not followed yet (from the old «Neft impulsu»)
  risk        CM-RISK-1 fear spike: VIX jumps and stocks fall together (safe-haven demand)
              CM-RISK-2 calm risk-on rally: stocks trend up while VIX is low (gold down; silver, platinum and
                        palladium are industrial metals: up)
              CM-CORR-1 gold stops moving against the dollar (60-candle correlation turns positive): both are bought
                        as havens — the metal's own trend continues
  industry    CM-CU-1  the copper / gold ratio turns (growth): gold down, the industrial metals up (only when the
                        broker has copper)
  pair        CM-LEAD-1 the pair metal (gold-silver, platinum-palladium) jumped, this one has not followed yet

The metal-ratio rule IM-RATIO-1 is shown on this block's page, but it keeps voting inside the technical block (it is
one of the twelve kinds of technical analysis there): one rule, one voice. Every rule here uses only candles that
had closed at that moment (the market's candle of the same time and earlier). The block reaches the forecasts as one
voice, «bazarlar» (one voice per family). Old methods «dollar», «oil», «risk» became CM-USD-2, CM-OIL-1, CM-RISK-1."""
from __future__ import annotations

import math
import time

from .db import DB

CM_VER = "2026-11-25.1"
TFS = ("1h", "4h", "1d")
FAMILY = {"CM-USD-1": "dollar", "CM-USD-2": "dollar", "CM-JPY-1": "dollar", "CM-CNH-1": "dollar",
          "CM-YLD-1": "faiz", "CM-OIL-1": "neft", "CM-RISK-1": "risk", "CM-RISK-2": "risk", "CM-CORR-1": "risk",
          "CM-CU-1": "sənaye", "CM-LEAD-1": "metal cütü"}
PAIR = {"XAU": "XAG", "XAG": "XAU", "XPT": "XPD", "XPD": "XPT"}
INDUSTRIAL = {"XAG", "XPT", "XPD"}
MOM_N, VOL_N, CORR_N = 20, 100, 60
MOM_Z = 1.5            # a trend «turns» when its scaled 20-candle move crosses ±1.5
JUMP_Z = 2.5           # a one-candle move of 2.5 of its usual size


def _rets(xs: list[float]) -> list[float]:
    return [math.log(b / a) if a > 0 and b > 0 else 0.0 for a, b in zip(xs, xs[1:])]


def _sd(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _corr(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 30:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    sa = sum((x - ma) ** 2 for x in a)
    sb = sum((x - mb) ** 2 for x in b)
    if sa <= 0 or sb <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sa * sb)


class Series:
    """One market's closes aligned to the metal's candle times (None where it has no candle)."""

    def __init__(self, closes: list[float | None]):
        self.c = closes

    def window(self, i: int, n: int) -> list[float] | None:
        """The last n+1 closes up to i (inclusive), or None if any is missing."""
        if i - n < 0:
            return None
        w = self.c[i - n:i + 1]
        return None if any(x is None for x in w) else w

    def mom_z(self, i: int) -> float | None:
        """The 20-candle log move divided by its usual size (one-candle volatility x sqrt 20)."""
        w = self.window(i, VOL_N)
        if not w:
            return None
        r = _rets(w)
        sd = _sd(r[:-MOM_N] or r)
        return (math.log(w[-1] / w[-1 - MOM_N]) / (sd * math.sqrt(MOM_N))) if sd > 0 and w[-1 - MOM_N] > 0 else None

    def jump_z(self, i: int) -> float | None:
        """The last candle's move divided by the usual size of the 100 before it."""
        w = self.window(i, VOL_N)
        if not w:
            return None
        r = _rets(w)
        sd = _sd(r[:-1])
        return r[-1] / sd if sd > 0 else None


def _crossed(z0: float | None, z1: float | None, lim: float) -> int:
    """+1 when z crosses above +lim, -1 below -lim, 0 otherwise (a turn, not every candle of a trend)."""
    if z0 is None or z1 is None:
        return 0
    if z0 < lim <= z1:
        return 1
    if z0 > -lim >= z1:
        return -1
    return 0


def _catch_up(metal: Series, other: Series, i: int) -> tuple[float, float] | None:
    """The metal's expected move from the other market's last move (beta over 100 candles) minus its real move, in
    units of the metal's usual move; and the link. None without a clear link."""
    a, b = metal.window(i, VOL_N), other.window(i, VOL_N)
    if not a or not b:
        return None
    g, x = _rets(a), _rets(b)
    c = _corr(x[:-1], g[:-1])
    if c is None or abs(c) < 0.2:
        return None
    mx = sum(x[:-1]) / len(x[:-1])
    sxx = sum((v - mx) ** 2 for v in x[:-1])
    if sxx <= 0:
        return None
    mg = sum(g[:-1]) / len(g[:-1])
    beta = sum((u - mx) * (v - mg) for u, v in zip(x[:-1], g[:-1])) / sxx
    sd = _sd(g[:-1])
    return ((beta * x[-1] - g[-1]) / sd if sd > 0 else 0.0), c


def detect(sym: str, i: int, m: dict[str, Series]) -> list[tuple[str, int, str]]:
    """Every cross-market rule on the metal's candle i. m: code -> Series aligned to the metal ('_metal', '_pair',
    DXY, EURUSD, USDJPY, USDCNH, OIL, BRENT, US500, VIX, US10Y, COPPER)."""
    out = []
    me = m["_metal"]
    # the dollar: DXY, or EUR/USD turned upside down when the broker has no DXY candle
    usd = m.get("DXY") if m.get("DXY") and m["DXY"].window(i, VOL_N) else None
    inv = 1
    if usd is None and m.get("EURUSD") and m["EURUSD"].window(i, VOL_N):
        usd, inv = m["EURUSD"], -1
    if usd is not None:
        z0, z1 = usd.mom_z(i - 1), usd.mom_z(i)
        d = _crossed(None if z0 is None else inv * z0, None if z1 is None else inv * z1, MOM_Z)
        if d:
            out.append(("CM-USD-1", -d, f"dollar trendi {'yuxarı' if d > 0 else 'aşağı'} döndü (20 şam, z {inv * z1:+.1f})"))
    best = None
    for code in ("DXY", "EURUSD", "USDJPY"):
        if m.get(code):
            r = _catch_up(me, m[code], i)
            if r and (best is None or abs(r[1]) > abs(best[1][1])):
                best = (code, r)
    if best and abs(best[1][0]) >= 1.0:
        gap, c = best[1]
        out.append(("CM-USD-2", 1 if gap > 0 else -1, f"{best[0]} tərpəndi, metal yetişməyib (əlaqə {c:+.2f}, fərq {gap:+.1f} σ)"))
    if m.get("USDJPY"):
        z = m["USDJPY"].jump_z(i)
        if z is not None and z <= -JUMP_Z:
            out.append(("CM-JPY-1", 1, f"yen kəskin bahalaşdı (USD/JPY {z:+.1f} σ): sığınacaq axını"))
    if m.get("USDCNH"):
        z0, z1 = m["USDCNH"].mom_z(i - 1), m["USDCNH"].mom_z(i)
        d = _crossed(z0, z1, MOM_Z)
        if d and sym == "XAU":
            out.append(("CM-CNH-1", d, f"yuan {'zəifləyir' if d > 0 else 'güclənir'} (USD/CNH 20 şam z {z1:+.1f})"))
    if m.get("US10Y"):
        z0, z1 = m["US10Y"].mom_z(i - 1), m["US10Y"].mom_z(i)
        d = _crossed(z0, z1, MOM_Z)
        if d:
            out.append(("CM-YLD-1", d, f"10 illik istiqrazın qiyməti {'qalxır (faiz enir)' if d > 0 else 'düşür (faiz qalxır)'}"))
    best = None
    for code in ("OIL", "BRENT"):
        if m.get(code):
            r = _catch_up(me, m[code], i)
            if r and (best is None or abs(r[1]) > abs(best[1][1])):
                best = (code, r)
    if best and abs(best[1][0]) >= 1.0:
        gap, c = best[1]
        out.append(("CM-OIL-1", 1 if gap > 0 else -1, f"neft ({best[0]}) tərpəndi, metal yetişməyib (əlaqə {c:+.2f}, fərq {gap:+.1f} σ)"))
    if m.get("VIX") and m.get("US500"):
        zv, zs = m["VIX"].jump_z(i), m["US500"].jump_z(i)
        if zv is not None and zs is not None and zv >= JUMP_Z and zs <= -2.0:
            out.append(("CM-RISK-1", 1, f"qorxu sıçrayışı: VIX {zv:+.1f} σ, S&P {zs:+.1f} σ"))
        z0, z1 = m["US500"].mom_z(i - 1), m["US500"].mom_z(i)
        w = m["VIX"].window(i, VOL_N)
        if w and _crossed(z0, z1, 2.0) == 1 and sorted(w).index(w[-1]) <= 0.2 * len(w):
            d = 1 if sym in INDUSTRIAL else -1
            out.append(("CM-RISK-2", d, f"sakit risk iştahı: S&P trendi güclü (z {z1:+.1f}), VIX aşağıdır"))
    if usd is not None:
        a, b = me.window(i, CORR_N), usd.window(i, CORR_N)
        a0, b0 = me.window(i - 1, CORR_N), usd.window(i - 1, CORR_N)
        if a and b and a0 and b0:
            c1, c0 = _corr(_rets(a), [inv * x for x in _rets(b)]), _corr(_rets(a0), [inv * x for x in _rets(b0)])
            mz = me.mom_z(i)
            if c0 is not None and c1 is not None and c0 <= 0.2 < c1 and mz is not None and abs(mz) >= 0.5:
                out.append(("CM-CORR-1", 1 if mz > 0 else -1, f"metal dollarla birlikdə hərəkət edir (əlaqə {c1:+.2f}): "
                                                               f"sığınacaq rejimi, öz trendi {'yuxarı' if mz > 0 else 'aşağı'}"))
    if m.get("COPPER") and sym in ("XAU", "XAG", "XPT", "XPD"):
        cu, au = m["COPPER"], m.get("_gold") or me
        a, b = cu.window(i, VOL_N), au.window(i, VOL_N)
        a0 = cu.window(i - 1, VOL_N)
        b0 = au.window(i - 1, VOL_N)
        if a and b and a0 and b0:
            ratio = Series([x / y for x, y in zip(a, b)])
            ratio0 = Series([x / y for x, y in zip(a0, b0)])
            d = _crossed(ratio0.mom_z(len(a0) - 1), ratio.mom_z(len(a) - 1), MOM_Z)
            if d:
                out.append(("CM-CU-1", d if sym in INDUSTRIAL else -d,
                            f"mis/qızıl nisbəti {'qalxır (böyümə)' if d > 0 else 'enir (yavaşlama)'}"))
    if m.get("_pair"):
        zp, zm = m["_pair"].jump_z(i), me.jump_z(i)
        if zp is not None and zm is not None and abs(zp) >= JUMP_Z and abs(zm) < 0.5:
            out.append(("CM-LEAD-1", 1 if zp > 0 else -1, f"cüt metal {zp:+.1f} σ tərpəndi, bu metal hələ yox ({zm:+.1f} σ)"))
    return out


CODES = ("DXY", "EURUSD", "USDJPY", "USDCNH", "OIL", "BRENT", "US500", "VIX", "US10Y", "COPPER")


def _series(db: DB, sym: str, tf: str, cs: list[dict], now: float) -> dict[str, Series]:
    from . import candles
    ts = [c["t"] for c in cs]
    m = {"_metal": Series([c["c"] for c in cs])}
    for code in CODES + (PAIR[sym], "XAU"):
        rows = {r["t"]: r["c"] for r in candles.closed(db, code, tf, now, limit=len(cs) + 50)}
        if len(rows) < VOL_N + 5:
            continue
        s = Series([rows.get(t) for t in ts])
        key = "_pair" if code == PAIR[sym] else "_gold" if code == "XAU" else code
        if key == "_gold" and sym == "XAU":
            continue
        m[key] = s
    return m


def run(db: DB, now: float | None = None) -> int:
    """Each metal and timeframe: the history once (per CM_VER), then the newest candles; next candle and stop + target
    exactly as for the technical rules."""
    from . import rules
    from .candles import METALS
    rules.ensure(db)
    now = time.time() if now is None else now
    added = 0
    for sym in METALS:
        for tf in TFS:
            cs = rules._load(db, sym, tf, now)
            if len(cs) < VOL_N + 30:
                continue
            mark = f"cm:ver:{CM_VER}:{sym}:{tf}"
            done = int(db.get(mark) or 0)
            m = _series(db, sym, tf, cs, now)
            ind = rules.Ind(cs)
            rows = []
            for i in range(VOL_N + 2, len(cs)):
                t = cs[i]["t"]
                if t <= done:
                    continue
                p1 = cs[i + 1]["c"] if i + 1 < len(cs) else None
                for rule, d, note in detect(sym, i, m):
                    rows.append((sym, tf, t, rule, d, cs[i]["c"], p1, "history" if not done else "live", note[:120],
                                 ind.atr[i], ind.adx[i]))
            db.executemany("INSERT OR IGNORE INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note, atr, "
                           "adx) VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
            added += len(rows)
            idx = {x["t"]: k for k, x in enumerate(cs)}
            upd = []
            for r in db.execute("SELECT t, rule, dir, price1 FROM rule_signals WHERE metal=? AND tf=? AND rule LIKE 'CM-%' "
                                "AND (price1 IS NULL OR rr IS NULL)", (sym, tf)).fetchall():
                k = idx.get(r["t"])
                if k is None:
                    continue
                p1 = cs[k + 1]["c"] if k + 1 < len(cs) else None
                res = rules.stop_target(cs, k, r["dir"], ind.atr[k]) if ind.atr[k] else None
                if p1 is not None or res:
                    upd.append((p1 if r["price1"] is None else r["price1"], res[0] if res else None,
                                res[1] if res else None, ind.atr[k], sym, tf, r["t"], r["rule"]))
            if upd:
                db.executemany("UPDATE rule_signals SET price1=?, rr=?, held=?, atr=? WHERE metal=? AND tf=? AND t=? "
                               "AND rule=?", upd)
            db.put(mark, str(cs[-2]["t"]))
    return added


def lookup(db: DB):
    from .rules import Lookup
    return Lookup(db, prefixes=("CM-",), name="bazarlar", families=FAMILY)


# ---------- the block's page (/bazarlar) ----------
def page(db: DB, sym: str, tf: str = "1h", now: float | None = None) -> dict:
    """The metal's chart with the rules' firings, each linked market next to the metal (how strongly it moves with
    it and whether it moves first), what the block says now and the book with the Judge's record."""
    import json as _json
    from . import candles, judge, markets, playbook, rules
    rules.ensure(db)
    now = time.time() if now is None else now
    tf = tf if tf in TFS else "1h"
    cs = [dict(r) for r in candles.closed(db, sym, tf, now, limit=600)]
    out: dict = {"symbol": sym, "tf": tf, "ts": now, "candles": cs}
    if not cs:
        return out
    idx = {c["t"]: i for i, c in enumerate(cs)}
    out["fired"] = [{"i": idx[r["t"]], "t": r["t"], "rule": r["rule"], "dir": r["dir"], "note": r["note"]}
                    for r in db.execute("SELECT t, rule, dir, note FROM rule_signals WHERE metal=? AND tf=? AND "
                                        "(rule LIKE 'CM-%' OR rule LIKE 'IM-%') AND t>=? ORDER BY t",
                                        (sym, tf, cs[0]["t"])).fetchall() if r["t"] in idx]
    rel = []
    for code, info in markets.RELATED.items():
        rows = {r["t"]: r["c"] for r in candles.closed(db, code, tf, now, limit=600)}
        pts = [[c["t"], rows[c["t"]]] for c in cs if c["t"] in rows]
        try:
            ln = markets.links(db, code, sym, now)
        except Exception:
            ln = {}
        rel.append({"code": code, "name": info["name"], "why": info["why"], "sign": info["sign"], "pts": pts,
                    "corr": ln.get("corr_1h"), "lead": ln.get("lead_15m"), "n": ln.get("n_1h")})
    out["markets"] = rel
    try:
        rec = _json.loads(db.get("ta:records") or "null")
    except ValueError:
        rec = None
    if not rec or now - rec.get("ts", 0) > 900:
        rec = {"ts": now, "r": rules.records(db).get("rules", {})}
        db.put("ta:records", _json.dumps(rec, ensure_ascii=False))
    out["book"] = [{"id": r["id"], "name": r["name"], "family": FAMILY.get(r["id"], "metal cütü" if r["id"].startswith("IM-") else None),
                    "how": r["how"], "signal": r["signal"], "void": r["void"], "source": r["source"],
                    "record": (rec["r"].get(r["id"]) or {}).get(tf), "voice": "texniki analiz" if r["id"].startswith("IM-") else "bazarlar"}
                   for r in playbook.RULES if r["area"] == "Bazarlar arası"]
    horizon = {"1h": "1h", "4h": "4h", "1d": "1d"}[tf]
    p, basis = rules.live_lookup(db, "cm").views(sym, now, horizon)["bazarlar"]
    st = {r["method"]: r for r in judge.stats(db, sym, horizon, "live", ttl=600)}
    hist = {r["method"]: r for r in judge.stats(db, sym, horizon, "history", ttl=600)}
    pick = lambda m_: (st.get(m_) if (st.get(m_) or {}).get("nh") else hist.get(m_)) or {}
    last_t = cs[-1]["t"]
    out["now"] = {"t": last_t, "vote": {"p": p, "basis": basis},
                  "rules": [f for f in out["fired"] if f["t"] == last_t],
                  "judge": {"bazarlar": {k: pick("bazarlar").get(k) for k in ("nh", "hit_rate", "bar", "status")}}}
    return out
