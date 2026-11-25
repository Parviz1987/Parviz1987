"""Forecast desks. Each horizon is forecast from the finished candles of its own size, and a forecast never uses data
from after its issue time. A horizon is (candle size, number of candles ahead): 3 days = 3 daily candles ahead.

Methods. Each has a reason to exist; the Judge decides which one, if any, may be trusted. A method with no view at
this moment says P = 0.5: the Judge then counts no hit or miss for it (only forecasts with a direction are judged).
- rw        «Dəyişməz»: no view of direction (P = 0.5). The honest baseline every method must beat.
- up        «Həmişə yuxarı»: the past share of up moves over the same distance. The second baseline.
- qaydalar  the technical-analysis block (rules.py, patterns.py): every chart rule of the Bilik kitabı (12 kinds)
            that fired on the newest closed candles votes, weighted by its own record known at that moment.
- chartist  the AI technical analyst reading the same block's facts.
- tsmom, trendmix (weeks to months) the long-horizon trend: 12-month and multi-speed.
- seans     (1 and 4 hours) Asian hours lean up, US hours down.
- surprise  (15 minutes to 1 day) US releases in the window before the forecast: the figure against the estimate and
            what that usually means for gold (app/surprise.py). No release in the window: no view.
- dollar, oil (15 minutes to 1 day) catch-up after a move in the dollar or oil that the metal has not followed yet
            (app/markets.py: the usual same-candle link is measured from the last 100 candles).
- news, strateq the brains as forecasters: the Reader's headline labels summed over the last hours, and the
            Strategist's own lean (app/brainviews.py). Judged like the rest: a brain earns trust only by results.
- consensus selective: each family of methods (one idea) gets one voice; a direction only when two independent
            families agree and none disagrees, outside high-impact releases and wild markets.
- macro     (daily and longer) the last week's change of the real interest rate and the dollar: both falling is good
            for gold. Needs FRED data; without it no view.
Every method gets the same range: an EWMA volatility (lambda 0.94) scaled to the horizon, with the width taken from
the past ratios of moves to volatility (fat tails), not from normal theory."""
from __future__ import annotations

import math

# horizon -> (candle size, candles ahead)
# No one-minute desk: a minute's move in gold (~1 $) is about twice the spread, and news reaches the brains 1-3
# minutes late. 15 and 30 minutes are the shortest horizons where a signal can arrive in time and beat the cost.
HORIZON_SPEC = {"15m": ("15m", 1), "30m": ("30m", 1), "1h": ("1h", 1), "4h": ("4h", 1), "1d": ("1d", 1), "3d": ("1d", 3),
                "1w": ("1w", 1),
                "10d": ("1d", 10), "1mo": ("1d", 21)}
HORIZONS = {h: tf for h, (tf, _) in HORIZON_SPEC.items()}      # horizon -> candle size it is built from
HORIZON_NAMES = {"15m": "15 dəqiqə", "30m": "30 dəqiqə", "1h": "1 saat", "4h": "4 saat (gün içi)", "1d": "1 gün", "3d": "3 gün",
                 "1w": "1 həftə", "10d": "10 gün",
                 "1mo": "1 ay"}
# One organ per idea (owner 2026-11-25: «one body, each part does its own job»). Chart reading lives in ONE place, the
# technical-analysis block (rules.py + patterns.py: 12 kinds, 33 rules), which reaches the forecasts as one voice,
# «qaydalar». The old chart methods (momentum, reversal, trend, breakout, rsi, fib, pullback, candles, ichimoku, metal
# ratio) were removed from the forecasts: each was a copy of a rule in the block (Ichimoku moved into it). «session»
# was a copy of «seans». Their past forecasts stay in the database; the long-horizon trend (tsmom, trendmix) stays:
# it works on weeks and months, which the block's candle rules do not cover.
METHODS = ("rw", "up", "tsmom", "fundamental", "surprise", "dollar", "oil", "risk", "xeber", "strateq", "brain2", "debate",
           "season", "jewel", "seans", "trendmix", "consensus", "garch", "gvz", "chartist", "qaydalar", "terazi", "vahid")
RETIRED = ("momentum", "reversal", "trend", "breakout", "rsi", "fib", "pullback", "session", "sam", "ichimoku", "pair",
           "macro", "cot",      # macro and COT: now rules of the fundamental block (FA-RY-1, FA-USD-1, FA-COT-1)
           "news")              # the headline sum: now the news block's rules (NW-*), its voice is «xeber»
# Families = the blocks (owner 2026-11-25: «every block one organ, one voice»; app/blocks.py). Methods of one block
# carry related ideas from the same kind of data: the consensus gives each block one voice and the Judge counts a
# block once in its multiple-testing bar. The AI analysts that read every block (Strateq, the second brain, the
# debate) are their own family.
FAMILY = {"qaydalar": "ta", "chartist": "ta", "tsmom": "ta", "trendmix": "ta",
          "fundamental": "fund", "surprise": "fund",
          "xeber": "news",
          "dollar": "cross", "oil": "cross", "risk": "cross",
          "seans": "time", "season": "time", "jewel": "time",
          "strateq": "brain", "brain2": "brain", "debate": "brain"}
FAMILY_NAMES = {"ta": "texniki analiz", "fund": "fundamental", "news": "xəbər", "cross": "bazarlar arası",
                "time": "vaxt və təqvim", "brain": "AI beyinlər"}
METHOD_NAMES = {"rw": "Dəyişməz (bazis)", "up": "Həmişə yuxarı (bazis)", "momentum": "Momentum",
                "reversal": "Qısa dönüş", "trend": "Trend (3 pəncərə)", "breakout": "Sıçrayış (20 şam)", "tsmom": "12 aylıq trend + istiqraz",
                "rsi": "RSI 30/70", "fib": "Fibonacci dönüşü", "pullback": "Trend içində geri çəkilmə", "macro": "Makro (real faiz + dollar)",
                "session": "Saat effekti", "surprise": "Hadisə sürprizi (ABŞ rəqəmləri)",
                "dollar": "Dollar impulsu", "oil": "Neft impulsu", "risk": "Risk əhvalı (VIX impulsu)",
                "xeber": "Xəbər (blokun qaydaları: əhval, Fed, rəqəm, geosiyasət, axın)", "strateq": "Strateqin fikri", "brain2": "İkinci beyin (OpenAI)", "debate": "Müzakirə (yuxarı ↔ aşağı)",
                "fundamental": "Fundamental (blokun qaydaları: faiz, Fed, dollar, COT, sürprizlər)", "seans": "Seans: Asiya ↑ / ABŞ ↓",
                "trendmix": "Çoxsürətli trend (dalğalanmaya görə)", "season": "Mövsümilik", "jewel": "Zərgərlik təqvimi",
                "sam": "Şam fiqurları", "ichimoku": "Ichimoku buludu", "pair": "Metal nisbəti (qızıl/gümüş, platin/palladium)",
                "garch": "GARCH dəyişkənlik aralığı", "gvz": "GVZ (opsionların gözlədiyi dəyişkənlik)",
                "chartist": "Qrafik analitiki (AI)",
                "qaydalar": "Qaydalar (Bilik kitabı, 12 növ)",
                "terazi": "Tərəzi (Hakimin çəkisi ilə)", "vahid": "Vahid proqnoz (hamısı birlikdə, öyrənən)",
                "consensus": "Seçici konsensus (müstəqil ailələr)"}
BASELINES = ("rw", "up")
MIN_CANDLES = 30                                       # fewer finished candles: no forecast
HISTORY_NEED = 200                                     # candles a desk is given (oldest first)
TSMOM_DAYS, TSMOM_WEEKS = 252, 52
Z50, Z80 = 0.6745, 1.2816
P_CAP = (0.35, 0.65)


def tf_of(h: str) -> str:
    return HORIZON_SPEC[h][0]


def steps_of(h: str) -> int:
    return HORIZON_SPEC[h][1]


def methods_for(h: str) -> tuple[str, ...]:
    out = list(METHODS)
    if tf_of(h) not in ("1d", "1w"):
        out.remove("fundamental")   # FRED, COT and the surprise index are daily-to-weekly drivers
    if h not in ("15m", "30m", "1h", "4h", "1d"):
        out.remove("surprise")
        out.remove("dollar")     # catch-up after a linked market's move: a short-horizon effect
        out.remove("oil")
        out.remove("risk")
        out.remove("xeber")      # headlines move prices for hours, not weeks
    if tf_of(h) not in ("1d", "1w"):
        out.remove("gvz")        # GVZ is a daily close
    if h not in ("1h", "4h", "1d"):
        out.remove("chartist")
        out.remove("strateq")
        out.remove("brain2")
        out.remove("debate")
    if h not in ("1h", "4h"):
        out.remove("seans")      # the overnight/day pattern lives inside a day
    if h not in ("1w", "10d", "1mo"):
        out.remove("trendmix")   # monthly seasons, festival seasons: weeks-to-months effects
        out.remove("season")
        out.remove("jewel")
        out.remove("tsmom")      # the 12-month trend is a weeks-to-months effect
    return tuple(out)


def target_time(issued_t: int, h: str) -> int:
    """When the forecast's target candle closes: k candles on; daily candles skip Saturday and Sunday."""
    from datetime import datetime, timezone
    tf, k = HORIZON_SPEC[h]
    step = {"15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}[tf]
    if tf != "1d":
        return issued_t + k * step
    t, left = issued_t, k
    while True:
        if datetime.fromtimestamp(t, timezone.utc).weekday() < 5:
            left -= 1
            if left == 0:
                return t + step
        t += step


def history_need(h: str) -> int:
    if h in ("10d", "1mo"):
        return TSMOM_DAYS + 10          # the 12-month trend needs a year of daily candles
    return HISTORY_NEED


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def log_returns(closes: list[float]) -> list[float]:
    return [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]


def ewma_sigma(rets: list[float], lam: float = 0.94) -> float:
    if not rets:
        return 0.0
    var = sum(r * r for r in rets[: min(10, len(rets))]) / min(10, len(rets))
    for r in rets:
        var = lam * var + (1 - lam) * r * r
    return math.sqrt(var)


def range_quantiles(rets: list[float], lam: float = 0.94) -> tuple[float, float]:
    """How wide the 50 % and 80 % ranges must be, in volatilities. Normal theory says 0.674 and 1.282, but metal
    moves have fat tails: most candles are quieter than the volatility suggests and a few are much bigger, so normal
    ranges catch too much at 50 %. Here each past move is divided by the volatility known just before it, and the
    ranges use the middle 50 % and 80 % of those past ratios (past data only). Few candles: normal theory."""
    if len(rets) < 60:
        return Z50, Z80
    warm = rets[:10]
    var = sum(r * r for r in warm) / len(warm)
    zs = []
    for r in rets[10:]:
        sd = math.sqrt(var)
        if sd > 0:
            zs.append(abs(r) / sd)
        var = lam * var + (1 - lam) * r * r
    if len(zs) < 50:
        return Z50, Z80
    zs.sort()
    q = lambda f: zs[min(len(zs) - 1, int(f * len(zs)))]
    # kept within a sane band around the normal values so one odd stretch cannot collapse or explode the ranges
    return min(max(q(0.5), Z50 * 0.5), Z50 * 1.5), min(max(q(0.8), Z80 * 0.5), Z80 * 1.5)


def _ema(xs: list[float], n: int) -> list[float]:
    k, e, out = 2 / (n + 1), sum(xs[:n]) / n, []
    for i, x in enumerate(xs):
        if i >= n:
            e = x * k + e * (1 - k)
        out.append(e if i >= n - 1 else float("nan"))
    return out


def tsmom_view(longer: list[dict], tf: str, bond: float | None) -> tuple[float, str]:
    """Time-series momentum (Moskowitz, Ooi, Pedersen 2012): the sign of the last 12 months' return predicts the next
    month, in commodities too; for gold, the Treasury trend adds information (a falling bond market is bad for gold).
    Up when gold's 12 months are up and bonds are not falling; down when both point down; disagreement: no view.
    Without bond data the gold trend alone speaks, more softly."""
    back = TSMOM_DAYS if tf == "1d" else TSMOM_WEEKS
    if len(longer) <= back:
        return 0.5, "12 aylıq tarixçə yoxdur"
    g = longer[-1]["c"] / longer[-1 - back]["c"] - 1
    if bond is None:
        p = 0.56 if g > 0 else 0.44
        return p, f"qızıl 12 ayda {g * 100:+.1f} %; istiqraz məlumatı yoxdur"
    if g > 0 and bond >= 0:
        return 0.6, f"qızıl 12 ayda {g * 100:+.1f} %, istiqraz {bond * 100:+.1f} %: ikisi də dəstəkləyir"
    if g < 0 and bond < 0:
        return 0.4, f"qızıl 12 ayda {g * 100:+.1f} %, istiqraz {bond * 100:+.1f} %: ikisi də aşağı"
    return 0.5, f"qızıl 12 ayda {g * 100:+.1f} %, istiqraz {bond * 100:+.1f} %: razı deyil"


ASIA_HOURS, US_HOURS = set(range(22, 24)) | set(range(0, 7)), set(range(14, 20))   # UTC


def seans_view(next_t: int | None, horizon: str) -> tuple[float, str]:
    """Overnight (Asian hours) gold has tended to rise and US-day gold to fall (Blose, Gondhalekar & Kort 2018; WGC
    2024 session attribution). Fixed in advance, never tuned: a window that starts in Asian hours leans up, one in US
    hours leans down, a little; London hours: no view."""
    if next_t is None:
        return 0.5, "vaxt məlumatı yoxdur"
    hour = (next_t // 3600) % 24
    if hour in ASIA_HOURS:
        return 0.53, f"{hour:02d}:00 UTC Asiya saatlarıdır: tarixən qızıl bu saatlarda qalxmağa meyllidir"
    if hour in US_HOURS:
        return 0.47, f"{hour:02d}:00 UTC ABŞ saatlarıdır: tarixən qızıl bu saatlarda zəifləməyə meyllidir"
    return 0.5, f"{hour:02d}:00 UTC London saatları: bu üsulun fikri yoxdur"


def trendmix_view(longer: list[dict], tf: str) -> tuple[float, str]:
    """Multi-speed, volatility-scaled trend (EWMAC, as in Carver's pysystemtrade; Hurst-Ooi-Pedersen): three pairs of
    exponential averages, each difference divided by the price's own volatility, averaged; scaled so a strong trend
    leans about 0.56. Fixed spans, never tuned on our data."""
    spans = ((8, 32), (16, 64), (32, 128)) if tf == "1d" else ((2, 8), (4, 16), (8, 32))
    closes = [c["c"] for c in longer]
    if len(closes) < spans[-1][1] + 20:
        return 0.5, f"tarixçə azdır ({len(closes)} şam)"

    def ema(xs, n):
        a, e = 2 / (n + 1), xs[0]
        for x in xs[1:]:
            e = a * x + (1 - a) * e
        return e
    rets = [b / a - 1 for a, b in zip(closes[-61:], closes[-60:]) if a]
    vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 * closes[-1] if rets else 0
    if not vol:
        return 0.5, "dalğalanma ölçülmədi"
    sig = [(ema(closes, f) - ema(closes, s_)) / vol for f, s_ in spans]
    score = max(-2.0, min(2.0, sum(sig) / len(sig) / 2))       # about -2..+2 for a strong trend
    if abs(score) < 0.25:
        return 0.5, f"trend zəifdir ({score:+.2f})"
    return round(0.5 + 0.03 * score, 4), f"üç sürətin orta trendi {score:+.2f} ({'yuxarı' if score > 0 else 'aşağı'})"


def _as_candles(seq) -> list[dict]:
    if seq and not isinstance(seq[0], dict):
        return [{"o": c, "h": c, "l": c, "c": c} for c in seq]
    return list(seq)


def _clip(p: float) -> float:
    return min(max(p, P_CAP[0]), P_CAP[1])


# ---------- Block 22: GARCH and GVZ ranges (the chart readings moved to the technical-analysis block) ----------
def garch_range(rets: list[float], price: float, k: int) -> dict:
    """GARCH(1,1) with fixed textbook weights (0.05 shock, 0.90 memory): tomorrow's variance from today's shock and
    the long-run level; the range over k candles from it. Only the range is tested (no direction)."""
    var_l = sum(r * r for r in rets) / len(rets)
    h = var_l
    for r in rets:
        h = 0.05 * var_l + 0.05 * r * r + 0.90 * h
    sk = math.sqrt(h * k)
    return {"lo50": price * math.exp(-0.6745 * sk), "hi50": price * math.exp(0.6745 * sk),
            "lo80": price * math.exp(-1.2816 * sk), "hi80": price * math.exp(1.2816 * sk)}


def gvz_range(gvz: float | None, price: float, days: float) -> dict | None:
    """GVZ: the volatility gold options expect (annual %); the range over `days` trading days from it."""
    if not gvz:
        return None
    sk = gvz / 100 * math.sqrt(days / 252)
    return {"lo50": price * math.exp(-0.6745 * sk), "hi50": price * math.exp(0.6745 * sk),
            "lo80": price * math.exp(-1.2816 * sk), "hi80": price * math.exp(1.2816 * sk)}


def weighted_view(out: dict, weights: dict | None) -> dict:
    """«Tərəzi»: every analyst's lean weighted by what the Judge measured for it on this desk (weights from
    learning.combine: Hedge weight > 1.05 and not below the bar in the long run, else 0). Live only: in the history replay the weights would
    come from the future, so there it stays without a view."""
    if not weights:
        return {"p_up": 0.5, "basis": "çəkilər yoxdur: Hakim hələ heç bir analitiki həddən yaxşı görməyib"}
    num = den = 0.0
    used = []
    for m, w in weights.items():
        v = out.get(m)
        if v and v["p_up"] != 0.5 and w > 0:
            num += w * (v["p_up"] - 0.5)
            den += w
            used.append(m)
    if not den:
        return {"p_up": 0.5, "basis": f"çəkisi olan analitiklərin ({len(weights)}) indi fikri yoxdur"}
    p = round(_clip(0.5 + num / den), 4)
    return {"p_up": p if abs(p - 0.5) >= 0.01 else 0.5,
            "basis": "çəki ilə: " + ", ".join(f"{METHOD_NAMES.get(m, m)} {weights[m]:.1f}" for m in used)}


def selective_consensus(out: dict, rets: list[float], sigma: float, event_near: bool) -> dict:
    """Quality over quantity. Each family (one idea) gets one voice: the average lean of its members that have a view.
    A direction only when at least two independent families lean the same way and no family leans against them,
    no high-impact US release is within the hour, and the market is not wild (volatility more than twice its usual).
    Otherwise no view: fewer forecasts, each with more behind it."""
    fam: dict[str, list[float]] = {}
    for m, v in out.items():
        if m in FAMILY and v["p_up"] != 0.5:
            fam.setdefault(FAMILY[m], []).append(v["p_up"] - 0.5)
    leans = {f: sum(x) / len(x) for f, x in fam.items()}
    if event_near:
        return {"p_up": 0.5, "basis": "yaxında mühüm ABŞ rəqəmi var: hadisədən əvvəl fikir bildirilmir"}
    usual = sorted(abs(r) for r in rets[-200:])
    usual = usual[len(usual) // 2] * 1.4826 if usual else 0.0      # a robust typical move (median-based)
    if usual and sigma > 2 * usual:
        return {"p_up": 0.5, "basis": "bazar həddindən artıq dalğalıdır: fikir bildirilmir"}
    ups = [f for f, x in leans.items() if x > 0]
    downs = [f for f, x in leans.items() if x < 0]
    side = ups if len(ups) >= len(downs) else downs
    other = downs if side is ups else ups
    names = ", ".join(FAMILY_NAMES[f] for f in sorted(side))
    if len(side) >= 2 and not other:
        lean = sum(leans[f] for f in side) / len(side)
        return {"p_up": round(_clip(0.5 + lean), 4),
                "basis": f"{len(side)} müstəqil ailə razıdır ({names}): {'yuxarı' if lean > 0 else 'aşağı'}"}
    if other and side:
        return {"p_up": 0.5, "basis": f"ailələr razı deyil (yuxarı {len(ups)}, aşağı {len(downs)})"}
    return {"p_up": 0.5, "basis": f"fikri olan müstəqil ailə azdır ({len(leans)})"}


def build(seq, horizon: str, macro: dict | None = None, next_t: int | None = None,
          releases: list[dict] | None = None, related: dict | None = None,
          views: dict | None = None, event_near: bool = False) -> dict | None:
    """All methods' forecasts for the close `steps_of(horizon)` candles ahead, from past candles (oldest first;
    plain closes are accepted too). macro: {"dfii10": weekly change, "dollar": weekly change in %} or None."""
    longer = _as_candles(seq)
    cands = longer[-HISTORY_NEED:]                     # every method but the hour-of-day one sees 200 candles
    if len(cands) < MIN_CANDLES:
        return None
    closes = [c["c"] for c in cands]
    rets = log_returns(closes)
    if len(rets) < MIN_CANDLES - 1:
        return None
    k = steps_of(horizon)
    tf = tf_of(horizon)
    sigma = ewma_sigma(rets) or 1e-6
    sk = sigma * math.sqrt(k)
    price = closes[-1]
    q50, q80 = range_quantiles(rets)
    span50, span80 = price * (math.exp(q50 * sk) - 1), price * (math.exp(q80 * sk) - 1)
    rng = {"lo50": price - span50, "hi50": price + span50, "lo80": price - span80, "hi80": price + span80}

    # «always up» over the same distance (k candles), from the past
    moves = [closes[i + k] - closes[i] for i in range(len(closes) - k)]
    moved = [m for m in moves if m != 0]
    up_share = sum(1 for m in moved if m > 0) / len(moved) if moved else 0.5

    out = {
        "rw": {"p_up": 0.5, "basis": f"istiqamət yoxdur; aralıq: volatillik {sigma * 100:.3f} % bir şamda"},
        "up": {"p_up": round(up_share, 4), "basis": f"keçmişdə {k} şamlıq hərəkətlərin {up_share * 100:.0f} %-i yuxarı"},
    }
    if "tsmom" in methods_for(horizon):
        p, basis = tsmom_view(longer, tf, (related or {}).get("bond"))
        out["tsmom"] = {"p_up": p, "basis": basis}
    if "trendmix" in methods_for(horizon):
        p, basis = trendmix_view(longer, tf)
        out["trendmix"] = {"p_up": p, "basis": basis}
    if "seans" in methods_for(horizon):
        p, basis = seans_view(next_t, horizon)
        out["seans"] = {"p_up": p, "basis": basis}

    if "surprise" in methods_for(horizon):
        if releases:
            score = sum(r["gold"] * r["weight"] for r in releases)
            names = ", ".join(f"{r['event']} ({'gözləntidən yuxarı' if r['above'] else 'gözləntidən aşağı'})"
                              for r in releases[-3:])
            out["surprise"] = {"p_up": round(_clip(0.5 + 0.06 * score), 4) if abs(score) >= 0.5 else 0.5,
                               "basis": f"{names}: qızıl üçün {'müsbət' if score > 0 else 'mənfi' if score < 0 else 'neytral'}"}
        else:
            out["surprise"] = {"p_up": 0.5, "basis": "bu müddətdə ABŞ rəqəmi açıqlanmayıb" if releases is not None
                               else "təqvim məlumatı yoxdur"}

    for key in ("dollar", "oil", "risk"):
        if key in methods_for(horizon):
            from .markets import impulse_view
            if related and key in related:
                g, x, name = related[key]
                p, basis = impulse_view(g, x, name)
            else:
                p, basis = 0.5, "bu bazarın şamı yoxdur"
            out[key] = {"p_up": p, "basis": basis}

    for key in ("xeber", "strateq", "brain2", "debate", "season", "jewel"):   # brainviews.py, slowviews.py
        if key in methods_for(horizon):
            p, basis = (views or {}).get(key, (0.5, "beyin məlumatı yoxdur"))
            out[key] = {"p_up": p, "basis": basis}

    if "fundamental" in methods_for(horizon):
        p, basis = (views or {}).get("fundamental", (0.5, "fundamental məlumat yoxdur"))
        out["fundamental"] = {"p_up": p, "basis": basis}
    mf = methods_for(horizon)
    if "garch" in mf:
        out["garch"] = {"p_up": 0.5, "basis": "yalnız aralıq: GARCH(1,1) dəyişkənliyi",
                        **garch_range(rets, price, k)}
    if "gvz" in mf:
        days = {"1d": 1, "3d": 3, "1w": 5, "10d": 10, "1mo": 21}.get(horizon, 1)
        gr = gvz_range((related or {}).get("gvz"), price, days)
        out["gvz"] = ({"p_up": 0.5, "basis": f"yalnız aralıq: opsionların gözlədiyi dəyişkənlik {related['gvz']:.1f} %",
                       **gr} if gr else {"p_up": 0.5, "basis": "GVZ yalnız qızılın opsion dəyişkənliyidir (və ya məlumat yoxdur)"})
    if "chartist" in mf:
        p, basis = (views or {}).get("chartist", (0.5, "Qrafik analitikinin yeni fikri yoxdur"))
        out["chartist"] = {"p_up": p, "basis": basis}
    if "qaydalar" in mf:
        p, basis = (views or {}).get("qaydalar", (0.5, "qayda məlumatı yoxdur"))
        out["qaydalar"] = {"p_up": p, "basis": basis}

    out["consensus"] = selective_consensus(out, rets, sigma, event_near)
    out["terazi"] = weighted_view(out, (views or {}).get("_weights"))
    from .unified import view as unified_view       # one forecast from every analyst, weights learned walk-forward
    out["vahid"] = unified_view((views or {}).get("_unified"), out)

    for v in out.values():          # a method with its own range (GARCH, GVZ) keeps it; all others use ours
        for key, val in rng.items():
            v.setdefault(key, val)
    return {"price": price, "sigma": sigma, "methods": out}


# Every method's passport: why it is here, what we expect, and what happens if it does not deliver. The Judge's
# current numbers are added next to it in the panel, so nothing in the system is there without a reason and a test.
PASSPORT = {
    "rw": {"why": "Dürüst başlanğıc: istiqamət yoxdur, yalnız aralıq.",
           "expect": "Aralıqlar 50 % və 80 % tutmalıdır.", "else": "Bazisdir, dəyişmir."},
    "up": {"why": "Metallar uzun müddətdə daha çox qalxıb: «həmişə yuxarı» ən sadə rəqibdir.",
           "expect": "Hər üsul bunu üstələməlidir.", "else": "Bazisdir, dəyişmir."},
    "tsmom": {"why": "Elmi sübutu ən güclü fikir: son 12 ayın istiqaməti növbəti ayı qabaqcadan deyir (Moskowitz, Ooi, "
                     "Pedersen 2012, 58 bazar, qızıl daxil). İstiqraz trendi qızıl üçün əlavə məlumat verir.",
              "expect": "1 həftə, 10 gün, 1 ay; qazancı əsasən böyük düşüşlərdən qaçmaqdan gəlir.",
              "else": "Bazar trendsiz dövrdədirsə zəifləyir; sübut olmasa konsensusdan çıxarılır."},
    "surprise": {"why": "ABŞ rəqəmi gözləntidən fərqli çıxanda dollar və qızıl dəqiqələr ərzində reaksiya verir.",
                 "expect": "15 dəqiqədən 4 saata qədər — ən güclü qısa siqnal namizədi.",
                 "else": "Fakt mənbəyi: FMP və ya beyin agenti (Rəqəm ovçusu)."},
    "dollar": {"why": "Qızıl dollarla qiymətlənir; dollar sıçrayanda qızıl çox vaxt bir neçə dəqiqə gec reaksiya verir.",
               "expect": "15 dəqiqə – 1 saat: ən real qısa siqnal namizədi.",
               "else": "Gecikmə yoxdursa (qızıl eyni anda reaksiya verirsə), çıxarılır; əlaqə yalnız ölçü kimi qalır. "
                       "Dolların üç ölçüsündən (indeks, EUR/USD, USD/JPY) son dövrdə qızılla ən bağlı olanı götürülür."},
    "oil": {"why": "Neft inflyasiya gözləntisini və geosiyasi qorxunu daşıyır; qızıl ona gec qoşula bilər.",
            "expect": "1 saat – 1 gün, xüsusən Yaxın Şərq xəbərlərində.",
            "else": "Çıxarılır; neft «Bazarlar» bölməsində ölçü kimi qalır."},
    "xeber": {"why": "Xəbər blokunun bir səsi: Oxuyucunun qiymətləndirdiyi başlıqlardan 7 qayda — əhval (mənfi xəbər 1,5 "
                     "qat, təsir 2 saatda yarıya sönür), mövzu üzrə (Fed, ABŞ rəqəmləri, geosiyasət, tələb-təklif), xəbər "
                     "axınının sıçrayışı və böyük xəbər; hər qayda Hakimdə ayrıca ölçülür, səsin gücü onun nəticəsidir.",
              "expect": "15 dəqiqə – 1 gün üfüqündə.", "else": "Sübut olmasa, vahid proqnozda çəkisi 0-a düşür."},
    "strateq": {"why": "Claude hər saat faktları (son hərəkətlər, dollar, neft, istiqraz, ABŞ rəqəmləri, xəbər) oxuyub 1 saat, 4 saat və 1 gün üçün yuxarı ehtimalı deyir: beynin özünü ölçürük.",
                "expect": "4 saat və 1 gün.",
                "else": "Strateq yalnız izahçı qalır, istiqamət soruşulmur (xərc azalır)."},
    "brain2": {"why": "Eyni sual və faktlar başqa şirkətin beyninə (OpenAI) ayrıca verilir: iki müstəqil beyin razı olanda "
                      "konsensusda görünür; hər biri ayrıca ölçülür.",
               "expect": "1 saat – 1 gün, xüsusən həyəcan (güclü xəbər, rəqəm) anlarında.",
               "else": "Sübut olmasa söndürülür (xərc azalır)."},
    "debate": {"why": "Bir beyin yuxarı, digəri aşağı üçün ən güclü dəlili gətirir; üçüncü beyin (başqa şirkət) dəlilləri "
                      "faktlarla tutuşdurub ehtimal verir (TradingAgents ideyası, Radar Gold arayışı).",
               "expect": "1 saat – 1 gün; xüsusən həyəcan anlarında tək beyindən yaxşı.",
               "else": "Tək beyinlərdən yaxşı deyilsə söndürülür (3 sorğu: xərc azalır)."},
    "seans": {"why": "Araşdırma: gecə (Asiya saatları) qızıl qalxmağa, ABŞ gündüzü zəifləməyə meyllidir (Blose və b. 2018; "
                     "WGC 2024). Əvvəlcədən sabitlənib, bizim məlumata uyğunlaşdırılmayıb.",
              "expect": "1 saat və 4 saat; kiçik, amma tez-tez.", "else": "Spred qazancı yeyirsə və ya sübut yoxdursa söndürülür."},
    "trendmix": {"why": "Ən güclü sübutu olan fikir (trend) daha dürüst formada: üç sürət, dalğalanmaya görə ölçülür "
                        "(Carver pysystemtrade; Hurst-Ooi-Pedersen). Əsas fərziyyə: 4 metal birlikdə.",
                 "expect": "1 həftə – 1 ay; tək metalda 51–53 %.", "else": "12 aylıq trenddən yaxşı deyilsə, çıxarılır."},
    "season": {"why": "Bəzi aylarda metal illər boyu eyni istiqamətdə gedib (məs. yanvar). Yalnız 5+ ilin 70 %-i razı olanda. "
                      "Dostun layihəsindən (#22) ideya.",
               "expect": "1 ay.", "else": "Çıxarılır."},
    "jewel": {"why": "Divali (qızıl, gümüş) və Çin Yeni ili (qızıl) öncəsi 21 gün zərgərlik alışı artır. Dostun "
                     "layihəsindən (#14) ideya; sahibin sahəsi.",
              "expect": "1 həftə – 1 ay; ildə iki pəncərə.", "else": "Çıxarılır."},
    "garch": {"why": "Dəyişkənlik dəstə-dəstə gəlir: GARCH sabahkı dəyişkənliyi bu günkü şokdan hesablayır.",
              "expect": "Aralıqlar 50 % və 80 % daha dəqiq tutmalıdır.", "else": "Bizim aralıqdan pisdirsə, istifadə olunmur."},
    "gvz": {"why": "Opsion bazarı qızılın nə qədər tərpənəcəyini qiymətə qoyur (GVZ indeksi).",
            "expect": "Gün və həftə aralıqlarını daha dəqiq tutmalıdır.", "else": "Bizim aralıqdan pisdirsə, istifadə olunmur."},
    "chartist": {"why": "AI analitik özü qrafikə baxır: bir neçə vaxt çərçivəsi, səviyyələr, fiqurlar, göstəricilər.",
                 "expect": "Texniki düsturlardan yaxşı olmalıdır.", "else": "Sübut olmasa, çəkisi 0 qalır."},
    "qaydalar": {"why": "Bilik kitabının 32 qaydası (texniki analizin 12 növü) bir səs: indi işə düşən hər qayda öz "
                        "istiqamətinə səs verir, səsin gücü həmin qaydanın o ana qədər bilinən nəticəsidir (50 %-dən "
                        "yaxşı olmayanın səsi yoxdur).",
                 "expect": "Tək qaydalardan və texniki düsturlardan yaxşı olmalıdır.",
                 "else": "Sübut olmasa, vahid proqnozda çəkisi 0-a düşür."},
    "fundamental": {"why": "Fundamental blokun bir səsi: real faiz (5 və 20 gün), Fed gözləntisi (2 illik faiz), "
                           "inflyasiya gözləntisi, geniş dollar, fondların mövqeyi və axını (COT), ABŞ sürpriz indeksi — "
                           "hər biri Bilik kitabında qayda, Hakim hər birini ayrıca ölçür; səsin gücü qaydanın o ana qədər "
                           "bilinən nəticəsidir.",
                    "expect": "Gün və həftə üfüqündə; WGC-nin GRAM amilləri.",
                    "else": "Sübut olmasa, vahid proqnozda çəkisi 0-a düşür."},
    "risk": {"why": "Risk və qeyri-müəyyənlik qızılın dörd əsas amilindən biridir (Dünya Qızıl Şurasının GRAM modeli): "
                    "qorxu indeksi (VIX) qəfil qalxanda sığınacaq tələbi artır. Qızıl hələ reaksiya verməyibsə, fərqin "
                    "bağlanması gözlənilir (dollar və neft impulsu ilə eyni üsul, əlaqə son 100 şamdan ölçülür).",
             "expect": "15 dəqiqə – 1 gün üfüqündə qorxu sıçrayışlarından sonra həddən yaxşı.",
             "else": "Sübut olmasa, vahid proqnozda çəkisi 0-a düşür."},
    "vahid": {"why": "Bütün analitiklərin və beyinlərin fikri bir ehtimalda: kimin nə qədər çəki alacağını sistem öz "
                     "keçmiş nəticələrindən addım-addım öyrənir (yalnız o anda bilinən nəticələrlə).",
              "expect": "Ayrı-ayrı analitiklərdən və tərəzidən yaxşı olmalıdır; öz-özünü sınaqda həddi keçməlidir.",
              "else": "Sübut gəlməsə, sadəcə göstərici qalır; heç bir qərara təsir etmir."},
    "terazi": {"why": "Hər analitikin (üsul, beyin) fikri Hakimin ölçdüyü nəticəyə görə çəki alır: düz deyənin sözü ağır, "
                      "həddən yaxşı olmayanınki sıfır. Yalnız canlı (keçmişdə çəki gələcəkdən gələrdi).",
               "expect": "Tək üsullardan yüksək düz çıxma faizi.", "else": "Çəki qaydası yalnız Hakimin rəqəmi ilə dəyişir."},
    "consensus": {"why": "Az, amma keyfiyyətli proqnoz: yalnız müstəqil fikir ailələri razı olanda, hadisə ərəfəsi və "
                         "həddən artıq dalğalı bazar xaricində. Eyni fikrin iki dəfə sayılmasının qarşısını alır.",
                  "expect": "Az proqnoz, amma tək üsullardan yüksək düz çıxma faizi.",
                  "else": "Ailələr və şərtlər yalnız Hakimin rəqəmi ilə dəyişdirilir; yenə yoxdursa, kart istiqamət göstərmir."},
}
