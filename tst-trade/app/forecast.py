"""Forecast desks. Each horizon is forecast from the finished candles of its own size, and a forecast never uses data
from after its issue time. A horizon is (candle size, number of candles ahead): 3 days = 3 daily candles ahead.

Methods. Each has a reason to exist; the Judge decides which one, if any, may be trusted. A method with no view at
this moment says P = 0.5: the Judge then counts no hit or miss for it (only forecasts with a direction are judged).
- rw        «Dəyişməz»: no view of direction (P = 0.5). The honest baseline every method must beat.
- up        «Həmişə yuxarı»: the past share of up moves over the same distance. The second baseline.
- momentum  the trend of the last L candles (time-series momentum: strong evidence at weeks to months).
- reversal  the opposite of the last candle (short-term reversal; only for one-candle horizons).
- trend     three windows (short, middle, long) vote up or down: a multi-window trend filter.
- breakout  the close broke the highest high / lowest low of the last 20 candles (Donchian channel).
- rsi       RSI(14) below 30 = oversold, expect up; above 70 = overbought, expect down; else no view.
- fib       the price came back to a Fibonacci level (38.2 / 50 / 61.8 %) of the last swing: expect a bounce in the
            swing's direction; elsewhere no view.
- session   (one hour) the same UTC hour's past up-share: metals are known to drift differently in Asian, London
            and New York hours. Shrunk toward 0.5 by its sample size.
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
METHODS = ("rw", "up", "momentum", "reversal", "trend", "breakout", "tsmom", "rsi", "fib", "pullback", "macro",
           "session", "surprise", "dollar", "oil", "news", "strateq", "brain2", "debate", "cot", "season", "jewel", "seans", "trendmix", "consensus",
           "sam", "ichimoku", "pair", "garch", "gvz", "chartist", "qaydalar", "terazi", "vahid")
# Families: methods that carry the SAME idea (momentum and trend are both "the move continues"). The consensus gives
# each family one voice, so one idea measured three ways cannot outvote two independent ideas.
FAMILY = {"chartist": "chart", "qaydalar": "rules", "sam": "revert", "ichimoku": "trend", "pair": "cross", "momentum": "trend", "trend": "trend", "breakout": "trend", "tsmom": "trend",
          "reversal": "revert", "rsi": "revert", "fib": "revert", "pullback": "revert",
          "dollar": "cross", "oil": "cross", "macro": "fund", "surprise": "fund",
          "news": "brain", "strateq": "brain", "brain2": "brain", "debate": "brain", "session": "time", "seans": "time", "trendmix": "trend", "cot": "position",
          "season": "calendar", "jewel": "calendar"}
FAMILY_NAMES = {"trend": "trend", "revert": "geri dönüş", "cross": "bazarlar arası", "fund": "fundamental",
                "brain": "beyinlər", "time": "vaxt", "position": "fond mövqeləri", "calendar": "təqvim",
                "chart": "qrafik analitiki", "rules": "Bilik kitabı qaydaları"}
METHOD_NAMES = {"rw": "Dəyişməz (bazis)", "up": "Həmişə yuxarı (bazis)", "momentum": "Momentum",
                "reversal": "Qısa dönüş", "trend": "Trend (3 pəncərə)", "breakout": "Sıçrayış (20 şam)", "tsmom": "12 aylıq trend + istiqraz",
                "rsi": "RSI 30/70", "fib": "Fibonacci dönüşü", "pullback": "Trend içində geri çəkilmə", "macro": "Makro (real faiz + dollar)",
                "session": "Saat effekti", "surprise": "Hadisə sürprizi (ABŞ rəqəmləri)",
                "dollar": "Dollar impulsu", "oil": "Neft impulsu",
                "news": "Xəbər əhvalı (Oxuyucu)", "strateq": "Strateqin fikri", "brain2": "İkinci beyin (OpenAI)", "debate": "Müzakirə (yuxarı ↔ aşağı)",
                "cot": "COT: fond mövqeləri", "seans": "Seans: Asiya ↑ / ABŞ ↓",
                "trendmix": "Çoxsürətli trend (dalğalanmaya görə)", "season": "Mövsümilik", "jewel": "Zərgərlik təqvimi",
                "sam": "Şam fiqurları", "ichimoku": "Ichimoku buludu", "pair": "Metal nisbəti (qızıl/gümüş, platin/palladium)",
                "garch": "GARCH dəyişkənlik aralığı", "gvz": "GVZ (opsionların gözlədiyi dəyişkənlik)",
                "chartist": "Qrafik analitiki (AI)",
                "qaydalar": "Qaydalar (Bilik kitabı, 12 növ)",
                "terazi": "Tərəzi (Hakimin çəkisi ilə)", "vahid": "Vahid proqnoz (hamısı birlikdə, öyrənən)",
                "consensus": "Seçici konsensus (müstəqil ailələr)"}
BASELINES = ("rw", "up")
LOOKBACK = {"15m": 16, "30m": 16, "1h": 24, "4h": 18, "1d": 20, "3d": 20, "1w": 12, "10d": 60, "1mo": 120}   # momentum window
TREND_WINDOWS = {"15m": (4, 16, 96), "30m": (4, 16, 96), "1h": (6, 24, 120), "4h": (6, 30, 120), "1d": (10, 50, 150),
                 "1w": (4, 13, 26)}
MIN_CANDLES = 30                                       # fewer finished candles: no forecast
HISTORY_NEED = 200                                     # candles a desk is given (oldest first)
SESSION_NEED = 1200
TSMOM_DAYS, TSMOM_WEEKS = 252, 52                                    # the hour-of-day method looks back ~7 weeks of hourly candles
Z50, Z80 = 0.6745, 1.2816
SHRINK = 0.25                                          # momentum and reversal move P(up) gently: P = Phi(SHRINK * z)
P_CAP = (0.35, 0.65)
SIGNAL_P = 0.6                                         # rule-based signals (breakout, rsi, fib): P = 0.6 or 0.4
FIB_LEVELS = (0.382, 0.5, 0.618)
FIB_SWING = 60


def tf_of(h: str) -> str:
    return HORIZON_SPEC[h][0]


def steps_of(h: str) -> int:
    return HORIZON_SPEC[h][1]


def methods_for(h: str) -> tuple[str, ...]:
    out = [m for m in METHODS if not (m == "reversal" and steps_of(h) > 1)]
    if tf_of(h) != "1d":
        out.remove("macro")      # FRED is daily: the macro view only for daily candles
    if h != "1h":
        out.remove("session")    # hour-of-day only for the one-hour desk
    if h not in ("15m", "30m", "1h", "4h", "1d"):
        out.remove("surprise")
        out.remove("dollar")     # catch-up after a linked market's move: a short-horizon effect
        out.remove("oil")
        out.remove("news")       # headlines move prices for hours, not weeks
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
        out.remove("trendmix")
        out.remove("cot")        # weekly positions, monthly seasons, festival seasons: weeks-to-months effects
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
    if h == "1h":
        return SESSION_NEED
    if h in ("10d", "1mo"):
        return TSMOM_DAYS + 10          # the 12-month trend needs a year of daily candles
    return HISTORY_NEED


def session_view(cands: list[dict], next_t: int | None) -> tuple[float, str]:
    """Up-share of past hourly candles that started at the same UTC hour as the next one."""
    if next_t is None or not cands or "t" not in cands[0]:
        return 0.5, "vaxt məlumatı yoxdur"
    hour = (next_t // 3600) % 24
    same = [c for c in cands if (c["t"] // 3600) % 24 == hour and c["c"] != c["o"]]
    n = len(same)
    if n < 15:
        return 0.5, f"{hour:02d}:00 UTC üçün keçmiş şam azdır ({n})"
    share = sum(1 for c in same if c["c"] > c["o"]) / n
    p = 0.5 + (share - 0.5) * n / (n + 40)
    if abs(p - 0.5) < 0.02:
        return 0.5, f"{hour:02d}:00 UTC: keçmişdə {share * 100:.0f} % yuxarı ({n} şam) — meyl yoxdur"
    return round(_clip(p), 4), f"{hour:02d}:00 UTC saatında keçmiş {n} şamın {share * 100:.0f} %-i yuxarı bağlanıb"


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


def rsi(closes: list[float], n: int = 14) -> float | None:
    """Wilder's RSI of the last close."""
    if len(closes) <= n:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[:n], closes[1:n + 1]):
        gains += max(b - a, 0)
        losses += max(a - b, 0)
    ag, al = gains / n, losses / n
    for a, b in zip(closes[n:], closes[n + 1:]):
        ag = (ag * (n - 1) + max(b - a, 0)) / n
        al = (al * (n - 1) + max(a - b, 0)) / n
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def fib_view(cands: list[dict], sigma: float) -> tuple[float, str]:
    """Bounce from a Fibonacci retracement of the last swing (FIB_SWING candles). Returns (P(up), basis)."""
    win = cands[-FIB_SWING:]
    if len(win) < 20:
        return 0.5, "swing üçün şam azdır"
    hi_i = max(range(len(win)), key=lambda i: win[i]["h"])
    lo_i = min(range(len(win)), key=lambda i: win[i]["l"])
    hi, lo, px = win[hi_i]["h"], win[lo_i]["l"], win[-1]["c"]
    span = hi - lo
    if span <= 0:
        return 0.5, "swing yoxdur"
    tol = max(px * sigma * 0.5, span * 0.02)
    up_swing = lo_i < hi_i                       # low came first: an up swing, levels measured down from the high
    for f in FIB_LEVELS:
        level = hi - f * span if up_swing else lo + f * span
        if abs(px - level) <= tol and min(hi_i, lo_i) < len(win) - 3 and max(hi_i, lo_i) < len(win) - 2:
            p = SIGNAL_P if up_swing else 1 - SIGNAL_P
            return p, f"qiymət {f * 100:.1f} % Fibonacci səviyyəsində ({level:.2f}); {'yuxarı' if up_swing else 'aşağı'} swing davamı gözlənilir"
    return 0.5, f"qiymət Fibonacci səviyyələrində deyil (swing {lo:.2f}–{hi:.2f})"


def _ema(xs: list[float], n: int) -> list[float]:
    k, e, out = 2 / (n + 1), sum(xs[:n]) / n, []
    for i, x in enumerate(xs):
        if i >= n:
            e = x * k + e * (1 - k)
        out.append(e if i >= n - 1 else float("nan"))
    return out


def pullback_view(cands: list[dict], sigma: float) -> tuple[float, str]:
    """A pullback inside a trend: the trend is up (close above EMA 50 and EMA 20 clearly above EMA 50), within the last
    5 candles the price dipped to the EMA 20 (the usual support in a trend), and the last candle closed up again
    above it: the trend is expected to resume. The mirror image for a down trend. Elsewhere no view."""
    if len(cands) < 60:
        return 0.5, "trend üçün şam azdır"
    closes = [c["c"] for c in cands]
    e20, e50 = _ema(closes, 20), _ema(closes, 50)
    px, last = closes[-1], cands[-1]
    tol = px * sigma * 0.5
    recent = cands[-5:]
    gap = px * sigma            # a real trend: the averages at least one typical candle apart (not flat noise)
    if px > e50[-1] and e20[-1] > e50[-1] + gap:
        touched = any(c["l"] <= e20[-5 + i] + tol for i, c in enumerate(recent))
        if touched and px > e20[-1] and last["c"] > last["o"]:
            return SIGNAL_P, "yuxarı trenddə qiymət EMA 20-yə endi və yenidən qalxır: trendin davamı gözlənilir"
        return 0.5, "yuxarı trend, amma geri çəkilmə və dönüş yoxdur"
    if px < e50[-1] and e20[-1] < e50[-1] - gap:
        touched = any(c["h"] >= e20[-5 + i] - tol for i, c in enumerate(recent))
        if touched and px < e20[-1] and last["c"] < last["o"]:
            return 1 - SIGNAL_P, "aşağı trenddə qiymət EMA 20-yə qalxdı və yenidən enir: trendin davamı gözlənilir"
        return 0.5, "aşağı trend, amma geri çəkilmə və dönüş yoxdur"
    return 0.5, "aydın trend yoxdur"


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


# ---------- Block 22 (owner 2026-11-24: «build them all»): more methods, each measured by the Judge ----------
def candle_pattern_view(cands: list[dict]) -> tuple[float, str]:
    """Şam fiqurları: the last candle's shape after a move. Engulfing and hammer / shooting star at the end of a
    3-candle run against it are the classic reversal signs; weak evidence in research, so a small lean."""
    if len(cands) < 6:
        return 0.5, "şam azdır"
    a, b = cands[-2], cands[-1]
    body, rng = abs(b["c"] - b["o"]), (b["h"] - b["l"]) or 1e-12
    run = cands[-5]["c"] - cands[-2]["c"]                 # >0: price fell into this candle
    if b["c"] > b["o"] and a["c"] < a["o"] and b["c"] >= a["o"] and b["o"] <= a["c"] and run > 0:
        return 0.55, "yuxarı udma (bullish engulfing) düşüşdən sonra"
    if b["c"] < b["o"] and a["c"] > a["o"] and b["c"] <= a["o"] and b["o"] >= a["c"] and run < 0:
        return 0.45, "aşağı udma (bearish engulfing) qalxışdan sonra"
    lower, upper = min(b["o"], b["c"]) - b["l"], b["h"] - max(b["o"], b["c"])
    if run > 0 and lower >= 2 * body and upper <= body and lower / rng > 0.55:
        return 0.54, "çəkic (hammer): aşağıdan alıcı çıxdı"
    if run < 0 and upper >= 2 * body and lower <= body and upper / rng > 0.55:
        return 0.46, "atan ulduz (shooting star): yuxarıdan satıcı çıxdı"
    return 0.5, "aydın fiqur yoxdur"


def ichimoku_view(cands: list[dict]) -> tuple[float, str]:
    """Ichimoku: price above the cloud and the fast line (9) above the slow line (26) = up; both below = down."""
    if len(cands) < 78:
        return 0.5, "şam azdır (78 lazımdır)"
    hi = lambda xs: max(c["h"] for c in xs)
    lo = lambda xs: min(c["l"] for c in xs)
    tenkan = (hi(cands[-9:]) + lo(cands[-9:])) / 2
    kijun = (hi(cands[-26:]) + lo(cands[-26:])) / 2
    past = cands[:-26]                                   # the cloud drawn 26 candles ago for «now»
    span_a = ((hi(past[-9:]) + lo(past[-9:])) / 2 + (hi(past[-26:]) + lo(past[-26:])) / 2) / 2
    span_b = (hi(past[-52:]) + lo(past[-52:])) / 2
    top, bot, price = max(span_a, span_b), min(span_a, span_b), cands[-1]["c"]
    if price > top and tenkan > kijun:
        return 0.55, "qiymət buluddan yuxarı, sürətli xətt yavaşdan yuxarı"
    if price < bot and tenkan < kijun:
        return 0.45, "qiymət buluddan aşağı, sürətli xətt yavaşdan aşağı"
    return 0.5, "qiymət buludun içində və ya xətlər ziddir"


def pair_view(pair: tuple | None) -> tuple[float, str]:
    """Metal nisbəti: this metal against its partner (gold/silver, platinum/palladium). When the ratio is far from its
    recent mean (|z| > 2 over the last 100 candles), a pull back towards the mean is expected: an expensive metal
    leans down, a cheap one up."""
    if not pair:
        return 0.5, "cüt metalın şamı yoxdur"
    g, o = pair
    rs = [math.log(a / b) for a, b in zip(g, o) if a and b]
    if len(rs) < 60:
        return 0.5, "cüt şam azdır"
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1)) or 1e-9
    z = (rs[-1] - m) / sd
    if z > 2:
        return 0.45, f"nisbət orta səviyyədən {z:.1f} sd yuxarıdır: bu metal cütünə görə bahadır"
    if z < -2:
        return 0.55, f"nisbət orta səviyyədən {abs(z):.1f} sd aşağıdır: bu metal cütünə görə ucuzdur"
    return 0.5, f"nisbət normaldır (z {z:+.1f})"


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

    lb = LOOKBACK[horizon]
    window = rets[-lb:]
    z_mom = sum(window) / (sigma * math.sqrt(len(window))) if window else 0.0
    out = {
        "rw": {"p_up": 0.5, "basis": f"istiqamət yoxdur; aralıq: volatillik {sigma * 100:.3f} % bir şamda"},
        "up": {"p_up": round(up_share, 4), "basis": f"keçmişdə {k} şamlıq hərəkətlərin {up_share * 100:.0f} %-i yuxarı"},
        "momentum": {"p_up": round(_clip(phi(SHRINK * z_mom)), 4),
                     "basis": f"son {len(window)} şamın hərəkəti {z_mom:+.2f}σ"},
    }
    if k == 1:
        z_rev = rets[-1] / sigma
        out["reversal"] = {"p_up": round(_clip(phi(-SHRINK * z_rev)), 4),
                           "basis": f"son şam {z_rev:+.2f}σ; əksinə gözlənilir"}

    wins = [w for w in TREND_WINDOWS[tf] if w < len(closes)]
    votes = [1 if closes[-1] > closes[-1 - w] else -1 if closes[-1] < closes[-1 - w] else 0 for w in wins]
    vs = sum(votes)
    out["trend"] = {"p_up": round(0.5 + 0.05 * vs, 4) if len(wins) == 3 else 0.5,
                    "basis": f"pəncərələr {', '.join(map(str, wins))}: səslər {'+'.join(map(str, votes)) if votes else '—'}"
                    if len(wins) == 3 else "uzun pəncərə üçün şam azdır"}

    prev = cands[-21:-1]
    hh, ll = max(c["h"] for c in prev), min(c["l"] for c in prev)
    if price > hh:
        out["breakout"] = {"p_up": SIGNAL_P, "basis": f"bağlanış 20 şamın ən yüksəyini ({hh:.2f}) keçdi"}
    elif price < ll:
        out["breakout"] = {"p_up": 1 - SIGNAL_P, "basis": f"bağlanış 20 şamın ən aşağısını ({ll:.2f}) qırdı"}
    else:
        out["breakout"] = {"p_up": 0.5, "basis": f"kanal içində ({ll:.2f}–{hh:.2f}): siqnal yoxdur"}

    r = rsi(closes)
    if r is None:
        out["rsi"] = {"p_up": 0.5, "basis": "RSI üçün şam azdır"}
    elif r < 30:
        out["rsi"] = {"p_up": SIGNAL_P, "basis": f"RSI {r:.0f}: həddən artıq satılıb, yuxarı dönüş gözlənilir"}
    elif r > 70:
        out["rsi"] = {"p_up": 1 - SIGNAL_P, "basis": f"RSI {r:.0f}: həddən artıq alınıb, aşağı dönüş gözlənilir"}
    else:
        out["rsi"] = {"p_up": 0.5, "basis": f"RSI {r:.0f}: neytral zona"}

    p, basis = fib_view(cands, sigma)
    out["fib"] = {"p_up": p, "basis": basis}
    p, basis = pullback_view(cands, sigma)
    out["pullback"] = {"p_up": p, "basis": basis}
    if "tsmom" in methods_for(horizon):
        p, basis = tsmom_view(longer, tf, (related or {}).get("bond"))
        out["tsmom"] = {"p_up": p, "basis": basis}
    if "trendmix" in methods_for(horizon):
        p, basis = trendmix_view(longer, tf)
        out["trendmix"] = {"p_up": p, "basis": basis}
    if "seans" in methods_for(horizon):
        p, basis = seans_view(next_t, horizon)
        out["seans"] = {"p_up": p, "basis": basis}

    if "session" in methods_for(horizon):
        last_t = cands[-1].get("t")
        if next_t is None and last_t is not None:
            next_t = last_t + 3600
        p, basis = session_view(longer, next_t)
        out["session"] = {"p_up": p, "basis": basis}

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

    for key in ("dollar", "oil"):
        if key in methods_for(horizon):
            from .markets import impulse_view
            if related and key in related:
                g, x, name = related[key]
                p, basis = impulse_view(g, x, name)
            else:
                p, basis = 0.5, "bu bazarın şamı yoxdur"
            out[key] = {"p_up": p, "basis": basis}

    for key in ("news", "strateq", "brain2", "debate", "cot", "season", "jewel"):   # brainviews.py, slowviews.py
        if key in methods_for(horizon):
            p, basis = (views or {}).get(key, (0.5, "beyin məlumatı yoxdur"))
            out[key] = {"p_up": p, "basis": basis}

    if "macro" in methods_for(horizon):
        if macro and macro.get("dfii10") is not None and macro.get("dollar") is not None:
            # A falling real rate (-0.10 pp) and a falling dollar (-1 %) are each worth about +0.05 of P(up).
            score = -macro["dfii10"] / 0.10 - macro["dollar"] / 1.0
            pm = round(_clip(0.5 + 0.05 * max(min(score, 3), -3)), 4)
            out["macro"] = {"p_up": pm if abs(score) >= 0.5 else 0.5,
                            "basis": f"həftədə real faiz {macro['dfii10']:+.2f} pp, dollar {macro['dollar']:+.2f} %"}
        else:
            out["macro"] = {"p_up": 0.5, "basis": "FRED məlumatı yoxdur"}

    mf = methods_for(horizon)
    if "sam" in mf:
        p, basis = candle_pattern_view(cands)
        out["sam"] = {"p_up": p, "basis": basis}
    if "ichimoku" in mf:
        p, basis = ichimoku_view(cands)
        out["ichimoku"] = {"p_up": p, "basis": basis}
    if "pair" in mf:
        p, basis = pair_view((related or {}).get("pair"))
        out["pair"] = {"p_up": p, "basis": basis}
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
    "momentum": {"why": "Trend davam etməyə meyllidir (həftə-ay üfüqündə güclü araşdırma dəlili).",
                 "expect": "1 həftə, 10 gün, 1 ay üfüqündə sübut.",
                 "else": "Qısa üfüqlərdə konsensusdan çıxarılmağa namizəd."},
    "reversal": {"why": "Qısa sıçrayış tez-tez geri qaytarılır.",
                 "expect": "15–30 dəqiqədə; amma spread çox vaxt qazancı yeyir.",
                 "else": "Spreaddən kiçikdirsə, çıxarılmağa namizəd."},
    "trend": {"why": "Üç pəncərə (qısa, orta, uzun) eyni istiqaməti göstərəndə trend daha etibarlıdır.",
              "expect": "1 gündən 1 aya qədər.", "else": "Pəncərələr dəyişdirilir və ya çıxarılır."},
    "breakout": {"why": "20 şamın ən yüksəyi və ya ən aşağısı qırılanda hərəkət sürətlənir.",
                 "expect": "4 saat və 1 gün; nadir, amma güclü siqnal.", "else": "Yalnız dalğalı bazarda saxlanılır."},
    "tsmom": {"why": "Elmi sübutu ən güclü fikir: son 12 ayın istiqaməti növbəti ayı qabaqcadan deyir (Moskowitz, Ooi, "
                     "Pedersen 2012, 58 bazar, qızıl daxil). İstiqraz trendi qızıl üçün əlavə məlumat verir.",
              "expect": "1 həftə, 10 gün, 1 ay; qazancı əsasən böyük düşüşlərdən qaçmaqdan gəlir.",
              "else": "Bazar trendsiz dövrdədirsə zəifləyir; sübut olmasa konsensusdan çıxarılır."},
    "rsi": {"why": "Çox alınmış və ya çox satılmış bazar geri dönməyə meyllidir.",
            "expect": "Sakit bazarda daha yaxşı.", "else": "Şərtli (sakit/dalğalı) yoxlamaya keçir."},
    "fib": {"why": "Treyderlər Fibonacci səviyyələrində alıb-satır, buna görə qiymət orada dayanır.",
            "expect": "1 saat və 4 saat.", "else": "Səviyyə dözümü dəyişdirilir və ya çıxarılır."},
    "macro": {"why": "Real faiz və dollar enəndə qızıl adətən qalxır (2022-dən zəifləyib).",
              "expect": "1 gündən 1 aya qədər.", "else": "Dərc gecikməsi nəzərə alınıb; yenə yoxdursa, çıxarılır."},
    "session": {"why": "Metallar Asiya, London və Nyu-York saatlarında fərqli hərəkət edir.",
                "expect": "1 saat.", "else": "Seans üzrə şərtli yoxlama ilə əvəz olunur."},
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
    "news": {"why": "Xəbərlər qiyməti saatlarla hərəkət etdirir; Oxuyucu hər başlığı metal, istiqamət və gücə görə qiymətləndirir.",
             "expect": "15 dəqiqə – 4 saat, xüsusən böyük xəbərdən sonra.",
             "else": "Oxuyucunun modeli dəyişdirilir və ya yalnız göstərici kimi qalır (xərc azalır)."},
    "strateq": {"why": "Claude hər saat faktları (son hərəkətlər, dollar, neft, istiqraz, ABŞ rəqəmləri, xəbər) oxuyub 1 saat, 4 saat və 1 gün üçün yuxarı ehtimalı deyir: beynin özünü ölçürük.",
                "expect": "4 saat və 1 gün.",
                "else": "Strateq yalnız izahçı qalır, istiqamət soruşulmur (xərc azalır)."},
    "pullback": {"why": "Treyderlərin ən çox işlətdiyi qurulum: trend içində qiymət dəstəyə (EMA 20) enir və trend "
                        "davam edir. Trend və dönüşün ayrı-ayrılıqda ~50 % verdiyi yerdə birləşmə daha dəqiq ola bilər.",
                 "expect": "1 saat – 1 gün; nadir siqnal.",
                 "else": "Konsensusdan çıxarılır; dözüm və EMA uzunluğu yalnız yeni sınaqla dəyişdirilir."},
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
    "cot": {"why": "Böyük fondlar həddən çox alanda (3 ilin 80 %-dən yuxarı) mövqe adətən açılır və qiymət geri çəkilir; "
                   "həddən çox satanda əksinə. Dostun 31 agentli layihəsindən (#15) ideya.",
            "expect": "1 həftə – 1 ay; nadir siqnal.", "else": "Çıxarılır; COT «Fundamental» bölməsində ölçü kimi qalır."},
    "season": {"why": "Bəzi aylarda metal illər boyu eyni istiqamətdə gedib (məs. yanvar). Yalnız 5+ ilin 70 %-i razı olanda. "
                      "Dostun layihəsindən (#22) ideya.",
               "expect": "1 ay.", "else": "Çıxarılır."},
    "jewel": {"why": "Divali (qızıl, gümüş) və Çin Yeni ili (qızıl) öncəsi 21 gün zərgərlik alışı artır. Dostun "
                     "layihəsindən (#14) ideya; sahibin sahəsi.",
              "expect": "1 həftə – 1 ay; ildə iki pəncərə.", "else": "Çıxarılır."},
    "sam": {"why": "Treyderlərin ən çox baxdığı şam fiqurları (udma, çəkic, atan ulduz) hərəkətdən sonra.",
            "expect": "Qısa üfüqdə dönüşü həddən yaxşı tutmalıdır.", "else": "Sübut olmasa, çəkisi 0 qalır."},
    "ichimoku": {"why": "Ichimoku buludu: trendin və onun gücünün klassik ölçüsü.",
                 "expect": "Trend üsulları kimi uzun üfüqdə sübut.", "else": "Sübut olmasa, çəkisi 0 qalır."},
    "pair": {"why": "Qızıl/gümüş və platin/palladium nisbəti adətən ortaya qayıdır: bahalanmış metal geri qalır.",
             "expect": "Nisbət uçlarda olanda həddən yaxşı.", "else": "Sübut olmasa, çəkisi 0 qalır."},
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
