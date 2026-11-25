"""Qayda dedektorları və ölçmə (Blocks 26 and 28): our own code finds the Bilik kitabı rules in the candles and the
Judge measures every rule on its own.

- Indicators are computed once per metal and timeframe (EMA 20/50/200, RSI 14, ATR 14, MACD 12/26/9, Bollinger
  20/2); detectors read them at candle i using candles up to i only (no look-ahead).
- Every firing is stored (rule_signals): metal, timeframe, the candle, the rule, the direction, the price at that close.
  The outcome is the next candle's close on the same timeframe (1 h, 4 h, 1 day).
- Self-simulation: on the first run the whole stored history is replayed (mode «history»), then every new closed candle
  is checked live (mode «live»).
- Record per rule and timeframe: hit rate, average result after the full cost, both halves of the period, p-value
  against a coin with a Bonferroni bar over all rule x timeframe cells. Analysts get this record next to each rule."""
from __future__ import annotations

import math
import time
from bisect import bisect_left

from .db import DB

TFS = ("1h", "4h", "1d")
SCHEMA = """
CREATE TABLE IF NOT EXISTS rule_signals (metal TEXT NOT NULL, tf TEXT NOT NULL, t INTEGER NOT NULL, rule TEXT NOT NULL,
  dir INTEGER NOT NULL, price0 REAL, price1 REAL, mode TEXT NOT NULL, note TEXT, PRIMARY KEY (metal, tf, t, rule));
CREATE INDEX IF NOT EXISTS rule_signals_r ON rule_signals(rule, tf);
"""
RULES_VER = "2026-11-25"     # a new detector set: each metal x timeframe replays its history once more (old rows kept)
RR_STOP, RR_TARGET, RR_BARS = 1.0, 2.0, 20      # the trader's test: stop 1 ATR, target 2 ATR, at most 20 candles
TF_DAYS = {"1h": 1 / 24, "4h": 1 / 6, "1d": 1.0}
PAIR = {"XAU": "XAG", "XAG": "XAU", "XPT": "XPD", "XPD": "XPT"}


def ensure(db: DB) -> None:
    db.script(SCHEMA)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(rule_signals)").fetchall()}
    for col, typ in (("atr", "REAL"), ("rr", "REAL"), ("held", "INTEGER")):
        if col not in cols:          # stop + target outcome (2026-11-25), in units of risk (R)
            db.script(f"ALTER TABLE rule_signals ADD COLUMN {col} {typ};")


def stop_target(cs: list[dict], i: int, d: int, atr: float) -> tuple[float, int] | None:
    """Enter at candle i's close in direction d; stop RR_STOP x ATR away, target RR_TARGET x ATR away. Walk the next
    candles: the stop counts first when one candle touches both (the cautious reading). Result in R (risk units) and
    the number of candles held; None until RR_BARS candles have closed."""
    if not atr or i + RR_BARS >= len(cs):
        return None
    e = cs[i]["c"]
    stop, target = e - d * RR_STOP * atr, e + d * RR_TARGET * atr
    for k in range(i + 1, i + RR_BARS + 1):
        x = cs[k]
        if (d > 0 and x["l"] <= stop) or (d < 0 and x["h"] >= stop):
            return -RR_STOP, k - i
        if (d > 0 and x["h"] >= target) or (d < 0 and x["l"] <= target):
            return RR_TARGET, k - i
    return (cs[i + RR_BARS]["c"] - e) * d / atr, RR_BARS


# ---------- indicators (whole series, computed once) ----------
def ema_series(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) < n:
        return out
    e = sum(xs[:n]) / n
    out[n - 1] = e
    k = 2 / (n + 1)
    for i in range(n, len(xs)):
        e += k * (xs[i] - e)
        out[i] = e
    return out


def rsi_series(xs: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) <= n:
        return out
    g = l = 0.0
    for i in range(1, n + 1):
        d = xs[i] - xs[i - 1]
        g += max(d, 0)
        l += max(-d, 0)
    g, l = g / n, l / n
    out[n] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    for i in range(n + 1, len(xs)):
        d = xs[i] - xs[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def atr_series(cs: list[dict], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(cs)
    trs = [cs[0]["h"] - cs[0]["l"]] + [max(c["h"] - c["l"], abs(c["h"] - p["c"]), abs(c["l"] - p["c"]))
                                       for p, c in zip(cs, cs[1:])]
    if len(trs) < n:
        return out
    a = sum(trs[:n]) / n
    out[n - 1] = a
    for i in range(n, len(trs)):
        a = (a * (n - 1) + trs[i]) / n
        out[i] = a
    return out


class Ind:
    def __init__(self, cs: list[dict]):
        self.cs = cs
        self.c = [x["c"] for x in cs]
        self.e20, self.e50, self.e200 = ema_series(self.c, 20), ema_series(self.c, 50), ema_series(self.c, 200)
        self.rsi = rsi_series(self.c)
        self.atr = atr_series(cs)
        e12, e26 = ema_series(self.c, 12), ema_series(self.c, 26)
        macd = [a - b if a is not None and b is not None else None for a, b in zip(e12, e26)]
        first = next((i for i, v in enumerate(macd) if v is not None), len(macd))
        sig = [None] * first + ema_series([v for v in macd[first:]], 9)
        self.hist = [m - s if m is not None and s is not None else None for m, s in zip(macd, sig)]
        self.bbw: list[float | None] = [None] * len(cs)
        self.bbu: list[float | None] = [None] * len(cs)
        self.bbl: list[float | None] = [None] * len(cs)
        s = s2 = 0.0
        for i, x in enumerate(self.c):
            s += x
            s2 += x * x
            if i >= 20:
                s -= self.c[i - 20]
                s2 -= self.c[i - 20] ** 2
            if i >= 19:
                m = s / 20
                sd = math.sqrt(max(s2 / 20 - m * m, 0))
                self.bbu[i], self.bbl[i], self.bbw[i] = m + 2 * sd, m - 2 * sd, (4 * sd / m if m else None)
        from .patterns import obv, stochastic
        self.sk, self.sd = stochastic(cs)
        self.obv = obv(cs)

    def trend(self, i: int) -> int:
        e20, e50, e200, c = self.e20[i], self.e50[i], self.e200[i], self.c[i]
        if None in (e20, e50, e200):
            return 0
        if c > e20 > e50 > e200:
            return 1
        if c < e20 < e50 < e200:
            return -1
        return 0


def _swings(cs: list[dict], lo: int, hi: int, k: int = 3) -> tuple[list[int], list[int]]:
    highs, lows = [], []
    for j in range(max(lo, k), hi - k):
        h, l = cs[j]["h"], cs[j]["l"]
        if all(h >= cs[j + d]["h"] for d in range(-k, k + 1) if d):
            highs.append(j)
        if all(l <= cs[j + d]["l"] for d in range(-k, k + 1) if d):
            lows.append(j)
    return highs, lows


def detect(ind: Ind, i: int, higher: dict | None = None, pair: tuple | None = None,
           tf: str = "1h") -> list[tuple[str, int, str]]:
    """The rules that fire at candle i (using candles 0..i only)."""
    cs, out = ind.cs, []
    if i < 210 or ind.atr[i] is None:
        return out
    c, atr, tr = cs[i], ind.atr[i], ind.trend(i)
    # TA-TREND-1
    if tr:
        out.append(("TA-TREND-1", tr, "EMA düzülüşü"))
    # TA-TREND-2 (only on the 1 h frame: the bigger frames give the direction)
    if higher is not None and tr and higher.get("4h") == tr and higher.get("1d") == tr:
        out.append(("TA-TREND-2", tr, "1 saat, 4 saat, 1 gün eyni istiqamətdə"))
    # swings and levels (last 100 candles, a swing needs 3 candles on each side: only confirmed ones)
    highs, lows = _swings(cs, i - 100, i + 1)
    # TA-SR-1
    near = 0.3 * atr
    sup = [cs[j]["l"] for j in lows if cs[j]["l"] < c["c"]]
    res = [cs[j]["h"] for j in highs if cs[j]["h"] > c["c"]]
    at_sup = any(abs(c["l"] - s) <= near for s in sup) and c["c"] > c["o"]
    at_res = any(abs(c["h"] - r) <= near for r in res) and c["c"] < c["o"]
    if at_sup and not at_res:
        out.append(("TA-SR-1", 1, "dəstəkdən alıcı şamı"))
    elif at_res and not at_sup:
        out.append(("TA-SR-1", -1, "müqavimətdən satıcı şamı"))
    # TA-BRK-1
    prev = cs[i - 20:i]
    if c["h"] - c["l"] > atr:
        if c["c"] > max(x["h"] for x in prev):
            out.append(("TA-BRK-1", 1, "20 şamın zirvəsi qırıldı"))
        elif c["c"] < min(x["l"] for x in prev):
            out.append(("TA-BRK-1", -1, "20 şamın dibi qırıldı"))
    # TA-RSI-1
    r0, r1 = ind.rsi[i - 1], ind.rsi[i]
    if r0 is not None and r1 is not None and 20 < r1 < 80:
        if tr > 0 and r0 < 40 and r1 > r0:
            out.append(("TA-RSI-1", 1, "yüksələn trenddə RSI 40-dan dönür"))
        elif tr < 0 and r0 > 60 and r1 < r0:
            out.append(("TA-RSI-1", -1, "enən trenddə RSI 60-dan dönür"))
    # TA-DIV-1 (two confirmed swings within the last 30 candles)
    h30 = [j for j in highs if j >= i - 30]
    l30 = [j for j in lows if j >= i - 30]
    if len(h30) >= 2 and ind.rsi[h30[-1]] and ind.rsi[h30[-2]]:
        a, b = h30[-2], h30[-1]
        if cs[b]["h"] > cs[a]["h"] and ind.rsi[b] < ind.rsi[a] and i - b <= 5:
            out.append(("TA-DIV-1", -1, "qiymət yeni zirvə, RSI aşağı"))
    if len(l30) >= 2 and ind.rsi[l30[-1]] and ind.rsi[l30[-2]]:
        a, b = l30[-2], l30[-1]
        if cs[b]["l"] < cs[a]["l"] and ind.rsi[b] > ind.rsi[a] and i - b <= 5:
            out.append(("TA-DIV-1", 1, "qiymət yeni dib, RSI yuxarı"))
    # TA-MACD-1
    h0, h1 = ind.hist[i - 1], ind.hist[i]
    if h0 is not None and h1 is not None and (h0 < 0 <= h1 or h0 > 0 >= h1):
        flips = sum(1 for j in range(i - 9, i + 1) if ind.hist[j - 1] is not None and ind.hist[j] is not None
                    and (ind.hist[j - 1] < 0) != (ind.hist[j] < 0))
        if flips < 3:
            out.append(("TA-MACD-1", 1 if h1 >= 0 else -1, "MACD histoqramı işarə dəyişdi"))
    # TA-BB-1
    ws = [w for w in ind.bbw[i - 100:i] if w is not None]
    if len(ws) >= 50 and ind.bbw[i - 1] is not None and ind.bbw[i - 1] <= sorted(ws)[len(ws) // 10]:
        if ind.bbu[i] is not None and c["c"] > ind.bbu[i]:
            out.append(("TA-BB-1", 1, "sıxılmadan sonra yuxarı bantdan çıxış"))
        elif ind.bbl[i] is not None and c["c"] < ind.bbl[i]:
            out.append(("TA-BB-1", -1, "sıxılmadan sonra aşağı bantdan çıxış"))
    # Fibonacci: the most important wave of the last 100 candles
    seg = range(i - 100, i + 1)
    jh = max(seg, key=lambda j: cs[j]["h"])
    jl = min(seg, key=lambda j: cs[j]["l"])
    hi, lo = cs[jh]["h"], cs[jl]["l"]
    wave = hi - lo
    fib_zone = None
    if wave >= 3 * atr and jh != jl:
        up_wave = jl < jh                              # a rise from the low to the high, now pulling back
        if up_wave and i > jh:
            ret = (hi - c["c"]) / wave
            fib_zone = (1, ret)
        elif not up_wave and i > jl:
            ret = (c["c"] - lo) / wave
            fib_zone = (-1, ret)
    turn_up, turn_dn = c["c"] > c["o"], c["c"] < c["o"]
    if fib_zone:
        d, ret = fib_zone
        if 0.382 <= ret <= 0.618 and ((d > 0 and turn_up) or (d < 0 and turn_dn)):
            out.append(("TA-FIB-1", d, f"dalğanın {ret * 100:.1f} %-i geri çəkilmə, dönüş şamı"))
        if tr == d and 0.236 <= ret < 0.382 and ((d > 0 and turn_up) or (d < 0 and turn_dn)):
            out.append(("TA-FIB-2", d, f"güclü trenddə dayaz geri çəkilmə {ret * 100:.1f} %"))
    # TA-CDL-1: a candle pattern at a level (support/resistance or the Fibonacci zone)
    from .forecast import candle_pattern_view
    p, why = candle_pattern_view(cs[i - 5:i + 1])
    if p != 0.5:
        d = 1 if p > 0.5 else -1
        at_level = (d > 0 and any(abs(c["l"] - s) <= near for s in sup)) or \
                   (d < 0 and any(abs(c["h"] - r) <= near for r in res)) or \
                   (fib_zone is not None and 0.382 <= fib_zone[1] <= 0.618)
        if at_level:
            out.append(("TA-CDL-1", d, why + " (səviyyədə)"))
    # IM-RATIO-1
    if pair:
        from .forecast import pair_view
        pp, why = pair_view(pair)
        if pp != 0.5:
            out.append(("IM-RATIO-1", 1 if pp > 0.5 else -1, why))
    from .patterns import more
    out.extend(more(ind, i, highs, lows, tf))
    return out


def _load(db: DB, sym: str, tf: str, now: float, limit: int = 4500) -> list[dict]:
    from . import candles
    return [dict(r) for r in candles.closed(db, sym, tf, now, limit=limit)]


def run(db: DB, now: float | None = None) -> dict:
    """Replay the history once (first run), then check the newest closed candles; score what has become known."""
    from .candles import METALS
    ensure(db)
    now = time.time() if now is None else now
    first_any = False
    added = 0
    for sym in METALS:
        data = {tf: _load(db, sym, tf, now) for tf in TFS}
        inds = {tf: Ind(cs) for tf, cs in data.items() if len(cs) > 220}
        other = {tf: {r["t"]: r["c"] for r in _load(db, PAIR[sym], tf, now)} for tf in inds}
        for tf, ind in inds.items():
            cs = ind.cs
            have = {r["t"] for r in db.execute("SELECT DISTINCT t FROM rule_signals WHERE metal=? AND tf=?",
                                                 (sym, tf)).fetchall()}
            # each metal and timeframe replays its own history once (a replay cut by a restart resumes here)
            first = db.execute("SELECT 1 FROM rule_signals WHERE metal=? AND tf=? AND mode='history' LIMIT 1",
                               (sym, tf)).fetchone() is None
            ver_key = f"rules:ver:{sym}:{tf}"
            if not first and db.get(ver_key) != RULES_VER:
                first, have = True, set()        # new detectors: replay; rows already there are kept (INSERT OR IGNORE)
            first_any = first_any or first
            start = 210 if first else max(210, len(cs) - 30)
            rows = []
            hi_ts = {h: [x["t"] for x in inds[h].cs] for h in ("4h", "1d") if h in inds}
            for i in range(start, len(cs)):
                t = cs[i]["t"]
                if t in have:
                    continue
                higher = None
                if tf == "1h" and len(hi_ts) == 2:
                    higher = {}
                    for h in ("4h", "1d"):
                        # the bigger frame's last candle CLOSED before this 1 h candle closed
                        j = bisect_left(hi_ts[h], t + 3600 - (14400 if h == "4h" else 86400) + 1) - 1
                        higher[h] = inds[h].trend(j) if j >= 210 else 0
                o = other.get(tf, {})
                pair = None
                pts = [(x["c"], o[x["t"]]) for x in cs[max(0, i - 100):i + 1] if x["t"] in o]
                if len(pts) >= 60 and cs[i]["t"] in o:
                    pair = ([a for a, _ in pts], [b for _, b in pts])
                p1 = cs[i + 1]["c"] if i + 1 < len(cs) else None
                for rule, d, note in detect(ind, i, higher, pair, tf):
                    rows.append((sym, tf, t, rule, d, cs[i]["c"], p1, "history" if first else "live", note[:120]))
            db.executemany("INSERT OR IGNORE INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note) "
                           "VALUES(?,?,?,?,?,?,?,?,?)", rows)
            added += len(rows)
            db.put(ver_key, RULES_VER)
            # the trader's test (stop + target) for every firing whose 20 candles have closed
            idx = {x["t"]: k for k, x in enumerate(cs)}
            upd = []
            for r in db.execute("SELECT t, rule, dir FROM rule_signals WHERE metal=? AND tf=? AND rr IS NULL AND t>=?",
                                (sym, tf, cs[0]["t"])).fetchall():
                k = idx.get(r["t"])
                if k is None or ind.atr[k] is None:
                    continue
                res = stop_target(cs, k, r["dir"], ind.atr[k])
                if res:
                    upd.append((ind.atr[k], res[0], res[1], sym, tf, r["t"], r["rule"]))
            if upd:
                db.executemany("UPDATE rule_signals SET atr=?, rr=?, held=? WHERE metal=? AND tf=? AND t=? AND rule=?",
                               upd)
            # score live firings whose next candle has closed since
            for r in db.execute("SELECT t FROM rule_signals WHERE metal=? AND tf=? AND price1 IS NULL",
                                (sym, tf)).fetchall():
                j = bisect_left([x["t"] for x in cs], r["t"])
                if j + 1 < len(cs) and cs[j]["t"] == r["t"]:
                    db.execute("UPDATE rule_signals SET price1=? WHERE metal=? AND tf=? AND t=? AND price1 IS NULL",
                               (cs[j + 1]["c"], sym, tf, r["t"]))
    fut = run_futures_volume(db)
    return {"added": added, "replay": first_any, "futures_volume": fut}


FUT_VOL_VER = "2026-11-25"


def _fut_candles(db: DB, sym: str, tf: str) -> list[dict]:
    """COMEX one-minute bars (Databento, real exchange volume) folded into 1 h / 4 h / 1 d candles (same buckets as
    ours: the daily candle follows the trading session)."""
    from .candles import bucket
    out: list[dict] = []
    for r in db.iterate("SELECT t, o, h, l, c, v FROM fut_candles WHERE symbol=? ORDER BY t", (sym,)):
        b = bucket(r["t"], tf)
        if out and out[-1]["t"] == b:
            x = out[-1]
            x["h"], x["l"], x["c"] = max(x["h"], r["h"]), min(x["l"], r["l"]), r["c"]
            x["v"] += r["v"] or 0
        else:
            out.append({"t": b, "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"] or 0})
    return [x for x in out if x["v"] > 0]


def run_futures_volume(db: DB) -> int:
    """Owner 2026-11-25: «don't wait months for volume». The volume rules run on COMEX futures candles (real volume):
    the two years already bought once, then each new day from the daily top-up. Stored as mode 'futures'; the next
    candle and the stop + target outcome are filled as soon as the candles exist. Live volume also comes from the
    tick count."""
    ensure(db)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='fut_candles'").fetchone():
        return 0
    added = 0
    from .candles import METALS
    for sym in METALS:
        for tf in TFS:
            mark = f"rules:futvol:{FUT_VOL_VER}:{sym}:{tf}"
            done = int(db.get(mark) or 0)
            newest = db.execute("SELECT MAX(t) t FROM fut_candles WHERE symbol=?", (sym,)).fetchone()["t"]
            if newest is None or newest <= done:
                continue
            cs = _fut_candles(db, sym, tf)
            if len(cs) < 320:
                continue
            ind = Ind(cs)
            rows = []
            for i in range(210, len(cs) - 1):        # the last candle may still be filling: not judged yet
                if cs[i]["t"] <= done:
                    continue
                for rule, d, note in detect(ind, i, None, None, tf):
                    if rule.startswith("VOL-"):
                        rows.append((sym, tf, cs[i]["t"], rule, d, cs[i]["c"], cs[i + 1]["c"], "futures",
                                     ("fyuçers: " + note)[:120], ind.atr[i]))
            db.executemany("INSERT OR IGNORE INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note, atr) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
            added += len(rows)
            idx = {x["t"]: k for k, x in enumerate(cs)}
            upd = []
            for r in db.execute("SELECT t, rule, dir FROM rule_signals WHERE metal=? AND tf=? AND mode='futures' "
                                "AND rr IS NULL", (sym, tf)).fetchall():
                k = idx.get(r["t"])
                res = stop_target(cs, k, r["dir"], ind.atr[k]) if k is not None and ind.atr[k] else None
                if res:
                    upd.append((res[0], res[1], sym, tf, r["t"], r["rule"]))
            if upd:
                db.executemany("UPDATE rule_signals SET rr=?, held=? WHERE metal=? AND tf=? AND t=? AND rule=?", upd)
            db.put(mark, str(cs[-2]["t"]))
    return added


def records(db: DB) -> dict:
    """Per rule and timeframe (all metals together): n, hit rate, average net result after the full cost, both
    halves, p against a coin, status with a Bonferroni bar over all cells."""
    from .judge import full_cost, _p_one_sided
    ensure(db)
    from .judge import COST, SLIP, SWAP, SWAP_GUESS
    cells: dict[tuple, list] = {}
    rr_cells: dict[tuple, list] = {}
    for r in db.iterate("SELECT metal, tf, t, rule, dir, price0, price1, atr, rr, held FROM rule_signals "
                        "WHERE price1 IS NOT NULL AND price0 > 0 ORDER BY t"):
        ret = (r["price1"] / r["price0"] - 1) * r["dir"]
        cells.setdefault((r["rule"], r["tf"]), []).append((r["t"], ret, ret - full_cost(r["metal"], r["tf"]), r["metal"]))
        if r["rr"] is not None and r["atr"]:
            # cost in risk units: spread + slippage once, the overnight fee for the candles held
            frac = COST.get(r["metal"], 0.0) * (1 + SLIP) + \
                r["held"] * TF_DAYS.get(r["tf"], 0.0) * SWAP.get(r["metal"], SWAP_GUESS)
            rr_cells.setdefault((r["rule"], r["tf"]), []).append(
                (r["rr"] - frac * r["price0"] / r["atr"], r["rr"] >= RR_TARGET, r["metal"], r["rr"]))
    bar = 0.05 / max(1, len(cells))
    out = {}
    for (rule, tf), v in cells.items():
        n = len(v)
        hits = sum(1 for _, ret, _, _ in v if ret > 0)
        net = sum(x for _, _, x, _ in v) / n
        half = n // 2
        h1 = sum(x for _, _, x, _ in v[:half]) / half if half else None
        h2 = sum(x for _, _, x, _ in v[half:]) / (n - half) if n - half else None
        by_metal: dict[str, list] = {}
        for _, ret, x, m in v:                     # each metal on its own: platinum's spread must not hide gold's result
            b = by_metal.setdefault(m, [0, 0, 0.0])
            b[0] += 1
            b[1] += int(ret > 0)
            b[2] += x
        p = _p_one_sided(hits, n, 0.5) if n >= 30 else None
        st = ("az" if n < 100 else
              "sübut" if p is not None and p < bar and net > 0 and h1 and h2 and h1 > 0 and h2 > 0 else
              "zəif" if hits / n < 0.5 and net < 0 else "yox")
        rv = rr_cells.get((rule, tf), [])
        rr = None
        if rv:
            m = len(rv)
            mean = sum(x[0] for x in rv) / m
            sd = math.sqrt(sum((x[0] - mean) ** 2 for x in rv) / (m - 1)) if m > 1 else 0.0
            half_r = m // 2
            a1 = sum(x[0] for x in rv[:half_r]) / half_r if half_r else None
            a2 = sum(x[0] for x in rv[half_r:]) / (m - half_r)
            bym: dict[str, list] = {}
            for net_r, win, mt, gross in rv:            # per metal: platinum's spread is ~30x gold's
                b = bym.setdefault(mt, [0, 0, 0.0, 0.0])
                b[0] += 1
                b[1] += int(win)
                b[2] += net_r
                b[3] += gross
            z = mean / (sd / math.sqrt(m)) if sd else 0.0
            p_r = 0.5 * math.erfc(z / math.sqrt(2))
            rr = {"n": m, "net_r": round(mean, 3), "target_share": round(sum(1 for x in rv if x[1]) / m, 3),
                  "gross_r": round(sum(x[3] for x in rv) / m, 3),
                  "by_metal": {mt: {"n": b[0], "target_share": round(b[1] / b[0], 3), "net_r": round(b[2] / b[0], 3),
                                    "gross_r": round(b[3] / b[0], 3)} for mt, b in bym.items()},
                  "p": round(p_r, 5), "status": ("az" if m < 100 else
                                                 "sübut" if p_r < bar and mean > 0 and a1 and a1 > 0 and a2 > 0 else
                                                 "yox")}
        out.setdefault(rule, {})[tf] = {"n": n, "hit_rate": round(hits / n, 4), "net_avg": round(net, 6), "rr": rr,
                                        "halves": [None if h1 is None else round(h1, 6),
                                                   None if h2 is None else round(h2, 6)],
                                        "p": None if p is None else round(p, 5), "status": st,
                                        "by_metal": {m: {"n": b[0], "hit_rate": round(b[1] / b[0], 4),
                                                         "net_avg": round(b[2] / b[0], 6)} for m, b in by_metal.items()}}
    return {"bar": bar, "rules": out}


def short_records(rec: dict) -> dict:
    """One line per rule for a brain's prompt: «1h 51 %/812 xərcdən sonra −0.010 % yox; 4h …»."""
    out = {}
    for rule, tfs in rec.get("rules", {}).items():
        out[rule] = "; ".join(f"{tf} {round(x['hit_rate'] * 100)} %/{x['n']} xərcdən sonra {x['net_avg'] * 100:+.3f} % "
                              f"{x['status']}" + (f", stop+hədəf: hədəfə çatdı {round(x['rr']['target_share'] * 100)} %, "
                                                  f"xərcdən sonra {x['rr']['net_r']:+.2f} R {x['rr']['status']}"
                                                  if x.get("rr") else "") for tf, x in sorted(tfs.items()))
    return out


def active_now(db: DB, sym: str) -> list[dict]:
    """The rules that fired on the latest closed candle of each timeframe (for the analysts and the page), and the
    futures volume rules of the newest futures candle when it is less than two days old."""
    ensure(db)
    out = []
    for tf in TFS:
        t = db.execute("SELECT MAX(t) t FROM rule_signals WHERE metal=? AND tf=? AND mode='futures'",
                       (sym, tf)).fetchone()["t"]
        if t is not None and t > time.time() - 2 * 86400:
            for r in db.execute("SELECT rule, dir, note FROM rule_signals WHERE metal=? AND tf=? AND t=? "
                                "AND mode='futures'", (sym, tf, t)).fetchall():
                out.append({"tf": tf, "t": t, "rule": r["rule"], "dir": r["dir"], "note": r["note"]})
        t = db.execute("SELECT MAX(t) t FROM rule_signals WHERE metal=? AND tf=? AND mode!='futures'",
                       (sym, tf)).fetchone()["t"]
        if t is None:
            continue
        for r in db.execute("SELECT rule, dir, note FROM rule_signals WHERE metal=? AND tf=? AND t=? "
                            "AND mode!='futures'", (sym, tf, t)).fetchall():
            out.append({"tf": tf, "t": t, "rule": r["rule"], "dir": r["dir"], "note": r["note"]})
    return out


# ---------- the rules as ONE analyst for the forecasts (owner 2026-11-25: «into our nervous system») ----------
TF_SEC = {"1h": 3600, "4h": 14400, "1d": 86400}
RULE_TFS = {"15m": ("1h",), "30m": ("1h",), "1h": ("1h",), "4h": ("1h", "4h")}      # longer horizons: 4h + 1d
LAG = 1800      # the rules job runs every 15 min and the live lookup is cached 10 min: a firing is used 30 min after its
                # candle closed, in the replay exactly as live (no history advantage)


class Lookup:
    """«Qaydalar»: every Bilik kitabı rule that fired on the newest closed candles votes in its direction, weighted by
    its OWN record known at that moment (walk-forward: an outcome counts only after its candle has closed, so the
    replay never uses the future). A rule with no edge so far (hit rate <= 50 %) gets no voice. Futures-only volume
    firings are left out (on live they arrive a day late)."""

    def __init__(self, db: DB):
        ensure(db)
        self.fire: dict[str, list] = {}                   # metal -> [(known_t, tf, rule, dir)] sorted
        out: dict[tuple, list] = {}                       # (rule, tf) -> [(outcome_known_t, hit)]
        for r in db.iterate("SELECT metal, tf, t, rule, dir, price0, price1 FROM rule_signals WHERE mode != 'futures'"):
            step = TF_SEC.get(r["tf"])
            if not step:
                continue
            self.fire.setdefault(r["metal"], []).append((r["t"] + step, r["tf"], r["rule"], r["dir"]))
            if r["price1"] is not None and r["price0"]:
                out.setdefault((r["rule"], r["tf"]), []).append((r["t"] + 2 * step,
                                                                 int((r["price1"] - r["price0"]) * r["dir"] > 0)))
        for v in self.fire.values():
            v.sort()
        self.fkeys = {m: [x[0] for x in v] for m, v in self.fire.items()}
        self.rec: dict[tuple, tuple[list, list]] = {}
        for k, v in out.items():
            v.sort()
            ts, cum, s = [], [], 0
            for t, h in v:
                s += h
                ts.append(t)
                cum.append(s)
            self.rec[k] = (ts, cum)

    def weight(self, rule: str, tf: str, t: float) -> tuple[float, int, float]:
        ts, cum = self.rec.get((rule, tf), ([], []))
        n = bisect_left(ts, t + 1)
        if not n:
            return 0.0, 0, 0.5
        hits = cum[n - 1]
        return max(0.0, 2 * (hits - n / 2) / (n + 50)), n, hits / n

    def views(self, metal: str, t: float, horizon: str) -> dict:
        tfs = RULE_TFS.get(horizon, ("4h", "1d"))
        keys = self.fkeys.get(metal, [])
        now_t = t - LAG
        lo = bisect_left(keys, now_t - max(TF_SEC[x] for x in tfs) + 1)
        hi = bisect_left(keys, now_t + 1)
        vote, used = 0.0, []
        for known, tf, rule, d in self.fire[metal][lo:hi] if keys else []:
            if tf not in tfs or known <= now_t - TF_SEC[tf]:
                continue                                  # only the newest closed candle of each timeframe
            w, n, hr = self.weight(rule, tf, now_t)
            if w <= 0:
                continue
            vote += d * w
            used.append((w, f"{rule} {tf} {'↑' if d > 0 else '↓'} ({round(hr * 100)} %/{n})"))
        if not used:
            return {"qaydalar": (0.5, "indi keçmişi müsbət olan qayda işə düşməyib")}
        p = round(0.5 + max(-0.15, min(0.15, 0.5 * vote)), 4)
        used.sort(reverse=True)
        return {"qaydalar": (p, f"{len(used)} qayda: " + ", ".join(x for _, x in used[:4]))}


_LIVE: dict = {"ts": 0.0, "lk": None}


def live_lookup(db: DB) -> Lookup:
    """Live forecasts reuse one Lookup for 10 minutes (it reads every rule firing)."""
    if _LIVE["lk"] is None or time.time() - _LIVE["ts"] > 600:
        _LIVE["lk"], _LIVE["ts"] = Lookup(db), time.time()
    return _LIVE["lk"]
