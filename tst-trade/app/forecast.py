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
- surprise  (1 minute to 1 day) US releases in the window before the forecast: the figure against the estimate and
            what that usually means for gold (app/surprise.py). No release in the window: no view.
- consensus the plain average of every other method's lean (P - 0.5) among those that have a view right now; no
            fitting to past results (so no hidden look-ahead). No view unless at least two methods agree in sum.
- macro     (daily and longer) the last week's change of the real interest rate and the dollar: both falling is good
            for gold. Needs FRED data; without it no view.
Every method gets the same range: an EWMA volatility (lambda 0.94) scaled to the horizon, with the width taken from
the past ratios of moves to volatility (fat tails), not from normal theory."""
from __future__ import annotations

import math

# horizon -> (candle size, candles ahead)
HORIZON_SPEC = {"1m": ("1m", 1), "1h": ("1h", 1), "4h": ("4h", 1), "1d": ("1d", 1), "3d": ("1d", 3),
                "1w": ("1w", 1),
                "10d": ("1d", 10), "1mo": ("1d", 21)}
HORIZONS = {h: tf for h, (tf, _) in HORIZON_SPEC.items()}      # horizon -> candle size it is built from
HORIZON_NAMES = {"1m": "1 dəqiqə", "1h": "1 saat", "4h": "4 saat (gün içi)", "1d": "1 gün", "3d": "3 gün",
                 "1w": "1 həftə", "10d": "10 gün",
                 "1mo": "1 ay"}
METHODS = ("rw", "up", "momentum", "reversal", "trend", "breakout", "rsi", "fib", "macro", "session", "surprise",
           "consensus")
METHOD_NAMES = {"rw": "Dəyişməz (bazis)", "up": "Həmişə yuxarı (bazis)", "momentum": "Momentum",
                "reversal": "Qısa dönüş", "trend": "Trend (3 pəncərə)", "breakout": "Sıçrayış (20 şam)",
                "rsi": "RSI 30/70", "fib": "Fibonacci dönüşü", "macro": "Makro (real faiz + dollar)",
                "session": "Saat effekti", "surprise": "Hadisə sürprizi (ABŞ rəqəmləri)",
                "consensus": "Konsensus (hamısı birlikdə)"}
BASELINES = ("rw", "up")
LOOKBACK = {"1m": 15, "1h": 24, "4h": 18, "1d": 20, "3d": 20, "1w": 12, "10d": 60, "1mo": 120}   # momentum window
TREND_WINDOWS = {"1m": (5, 15, 60), "1h": (6, 24, 120), "4h": (6, 30, 120), "1d": (10, 50, 150),
                 "1w": (4, 13, 26)}
MIN_CANDLES = 30                                       # fewer finished candles: no forecast
HISTORY_NEED = 200                                     # candles a desk is given (oldest first)
SESSION_NEED = 1200                                    # the hour-of-day method looks back ~7 weeks of hourly candles
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
    if h not in ("1m", "1h", "4h", "1d"):
        out.remove("surprise")   # a release moves the next minutes to a day; longer horizons drown it
    return tuple(out)


def target_time(issued_t: int, h: str) -> int:
    """When the forecast's target candle closes: k candles on; daily candles skip Saturday and Sunday."""
    from datetime import datetime, timezone
    tf, k = HORIZON_SPEC[h]
    step = {"1m": 60, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800}[tf]
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
    return SESSION_NEED if h == "1h" else HISTORY_NEED


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


def _as_candles(seq) -> list[dict]:
    if seq and not isinstance(seq[0], dict):
        return [{"o": c, "h": c, "l": c, "c": c} for c in seq]
    return list(seq)


def _clip(p: float) -> float:
    return min(max(p, P_CAP[0]), P_CAP[1])


def build(seq, horizon: str, macro: dict | None = None, next_t: int | None = None,
          releases: list[dict] | None = None) -> dict | None:
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

    if "macro" in methods_for(horizon):
        if macro and macro.get("dfii10") is not None and macro.get("dollar") is not None:
            # A falling real rate (-0.10 pp) and a falling dollar (-1 %) are each worth about +0.05 of P(up).
            score = -macro["dfii10"] / 0.10 - macro["dollar"] / 1.0
            pm = round(_clip(0.5 + 0.05 * max(min(score, 3), -3)), 4)
            out["macro"] = {"p_up": pm if abs(score) >= 0.5 else 0.5,
                            "basis": f"həftədə real faiz {macro['dfii10']:+.2f} pp, dollar {macro['dollar']:+.2f} %"}
        else:
            out["macro"] = {"p_up": 0.5, "basis": "FRED məlumatı yoxdur"}

    views = {m: v["p_up"] - 0.5 for m, v in out.items() if m not in ("rw", "up") and v["p_up"] != 0.5}
    if len(views) >= 2 and abs(sum(views.values()) / len(views)) >= 0.01:
        lean = sum(views.values()) / len(views)
        ups = sorted(m for m, d in views.items() if d > 0)
        downs = sorted(m for m, d in views.items() if d < 0)
        out["consensus"] = {"p_up": round(_clip(0.5 + lean), 4),
                            "basis": f"{len(views)} üsulun ortası: yuxarı {len(ups)}, aşağı {len(downs)}"}
    else:
        out["consensus"] = {"p_up": 0.5, "basis": f"fikri olan üsul azdır və ya fikirlər bir-birini sıfırlayır ({len(views)})"}

    for v in out.values():
        v.update(rng)
    return {"price": price, "sigma": sigma, "methods": out}
