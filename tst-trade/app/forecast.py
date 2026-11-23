"""Forecast desks. Each horizon is forecast from the finished candles of its own size (1m from 1m candles, 1h from
1h candles, 1d from daily, 1w from weekly), so a forecast never uses data from after its issue time.

Methods (only ones with a reason to exist; the Judge decides which one, if any, may be trusted):
- rw       «Dəyişməz»: no view of direction (P = 0.5). The honest baseline every method must beat.
- up       «Həmişə yuxarı»: the up-share of the past candles. The second baseline.
- momentum «Momentum»: the trend of the last L candles (time-series momentum: strong evidence at weeks-months).
- reversal «Qısa dönüş»: the opposite of the last candle (short-term reversal: mixed evidence, costs eat it).
Every method gets the same range: an EWMA volatility (lambda 0.94) scaled to one candle, normal quantiles."""
from __future__ import annotations

import math

HORIZONS = {"1m": "1m", "1h": "1h", "1d": "1d", "1w": "1w"}      # horizon -> candle size it is built from
HORIZON_NAMES = {"1m": "1 dəqiqə", "1h": "1 saat", "1d": "1 gün", "1w": "1 həftə"}
METHODS = ("rw", "up", "momentum", "reversal")
METHOD_NAMES = {"rw": "Dəyişməz (bazis)", "up": "Həmişə yuxarı (bazis)", "momentum": "Momentum", "reversal": "Qısa dönüş"}
BASELINES = ("rw", "up")
LOOKBACK = {"1m": 15, "1h": 24, "1d": 20, "1w": 12}   # momentum window in candles
MIN_CANDLES = 30                                       # fewer finished candles: no forecast
Z50, Z80 = 0.6745, 1.2816
SHRINK = 0.25                                          # momentum and reversal move P(up) gently: P = Phi(SHRINK * z)
P_CAP = (0.35, 0.65)


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


def _clip(p: float) -> float:
    return min(max(p, P_CAP[0]), P_CAP[1])


def build(closes: list[float], horizon: str) -> dict | None:
    """All methods' forecasts for the next candle, from past closes (oldest first). None: not enough data."""
    if len(closes) < MIN_CANDLES:
        return None
    rets = log_returns(closes)
    if len(rets) < MIN_CANDLES - 1:
        return None
    sigma = ewma_sigma(rets)
    price = closes[-1]
    if sigma <= 0:
        sigma = 1e-6
    span50, span80 = price * (math.exp(Z50 * sigma) - 1), price * (math.exp(Z80 * sigma) - 1)
    rng = {"lo50": price - span50, "hi50": price + span50, "lo80": price - span80, "hi80": price + span80}
    moved = [r for r in rets if r != 0]
    up_share = sum(1 for r in moved if r > 0) / len(moved) if moved else 0.5
    lb = LOOKBACK[horizon]
    window = rets[-lb:]
    z_mom = sum(window) / (sigma * math.sqrt(len(window))) if window else 0.0
    z_rev = rets[-1] / sigma
    out = {
        "rw": {"p_up": 0.5, "basis": f"istiqamət yoxdur; aralıq: volatillik {sigma * 100:.3f} % bir şamda"},
        "up": {"p_up": round(up_share, 4), "basis": f"son {len(moved)} şamın {up_share * 100:.0f} %-i yuxarı bağlanıb"},
        "momentum": {"p_up": round(_clip(phi(SHRINK * z_mom)), 4),
                     "basis": f"son {len(window)} şamın hərəkəti {z_mom:+.2f}σ"},
        "reversal": {"p_up": round(_clip(phi(-SHRINK * z_rev)), 4),
                     "basis": f"son şam {z_rev:+.2f}σ; əksinə gözlənilir"},
    }
    for v in out.values():
        v.update(rng)
    return {"price": price, "sigma": sigma, "methods": out}
