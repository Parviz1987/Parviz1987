"""Related markets: what moves gold, from the same Capital.com stream (no new source, no new cost).

Every market here has a passport: why it is linked to gold and which sign the link should have. The link itself is
not assumed: it is measured (correlation of returns) and tested (does it move BEFORE gold? the impulse methods in
the Judge). Broker market names (epics) are not guessed: each is checked against the broker's own market list."""
from __future__ import annotations

import json
import logging
import math
import time

import httpx

from . import candles
from .db import DB

log = logging.getLogger("tst.markets")

# code -> name, broker epics to try (first that exists), search words, why it matters, expected sign with gold
RELATED = {
    "DXY": {"name": "Dollar indeksi", "epics": ["DXY", "DOLLAR", "USDX"], "search": "dollar index",
            "why": "Qızıl dollarla qiymətlənir: dollar bahalaşanda qızıl başqa valyutalarda bahalaşır, tələb azalır.",
            "sign": -1},
    "EURUSD": {"name": "EUR/USD", "epics": ["EURUSD"], "search": "EUR/USD",
               "why": "Dolların əsas cütü: avro qalxanda dollar zəifləyir, bu, qızıl üçün adətən müsbətdir.", "sign": +1},
    "USDJPY": {"name": "USD/JPY", "epics": ["USDJPY"], "search": "USD/JPY",
               "why": "Dollar və ABŞ faizlərinin həssas göstəricisi; yen də qızıl kimi sığınacaqdır.", "sign": -1},
    "OIL": {"name": "Neft (WTI)", "epics": ["OIL_CRUDE", "CRUDE", "WTI", "USOIL"], "search": "crude oil",
            "why": "Neft bahalaşanda inflyasiya gözləntisi artır: qızıl inflyasiyadan qoruyan aktiv kimi alınır.",
            "sign": +1},
    "BRENT": {"name": "Neft (Brent)", "epics": ["OIL_BRENT", "BRENT", "UKOIL"], "search": "brent",
              "why": "Dünya neft qiymətinin əsası; Yaxın Şərq gərginliyi əvvəl buraya, sonra qızıla düşür.",
              "sign": +1},
    "US500": {"name": "S&P 500", "epics": ["US500", "SPX500", "SP500"], "search": "US 500",
              "why": "Risk iştahı: səhmlər kəskin düşəndə pul sığınacağa (qızıla) qaçır; adi günlərdə əlaqə zəifdir.",
              "sign": 0},
    "VIX": {"name": "VIX (qorxu)", "epics": ["VIX"], "search": "volatility index",
            "why": "Bazarın qorxu ölçüsü: qorxu artanda sığınacaq tələbi artır.", "sign": +1},
    # The broker has the 10-year Treasury note FUTURE (a price), not the yield: the price falls when the yield rises.
    "US10Y": {"name": "ABŞ 10 illik istiqraz (qiymət)", "epics": ["US10Y", "TNOTE", "UST10Y", "T-NOTE"],
              "search": "10-year",
              "why": "Faiz qalxanda bu istiqrazın qiyməti düşür və qızıl saxlamağın «itirilmiş gəliri» artır: "
                     "istiqraz qiyməti qalxanda (faiz enəndə) qızıl üçün adətən müsbətdir.", "sign": +1},
}
HISTORY_TF = {"15m": 1000, "30m": 1000, "1h": 1000, "4h": 1000, "1d": 1000}
RESOLVE_EVERY = 86400


async def resolve(base: str, tokens: dict) -> dict[str, str]:
    """code -> epic, only for markets the broker really has (GET /markets/{epic}, else a search)."""
    out: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=15.0) as c:
        for code, m in RELATED.items():
            for epic in m["epics"]:
                r = await c.get(f"{base}/markets/{epic}", headers=tokens)
                if r.status_code == 200:
                    out[code] = epic
                    break
            if code in out:
                continue
            r = await c.get(f"{base}/markets", params={"searchTerm": m["search"]}, headers=tokens)
            if r.status_code == 200:
                found = (r.json() or {}).get("markets") or []
                if found and isinstance(found[0], dict) and found[0].get("epic"):
                    out[code] = str(found[0]["epic"])
    return out


def saved(db: DB) -> dict:
    return json.loads(db.get("related:epics") or "{}")


def _rets(rows: list[dict]) -> dict[int, float]:
    return {b["t"]: math.log(b["c"] / a["c"]) for a, b in zip(rows, rows[1:]) if a["c"] > 0 and b["c"] > 0}


def _corr(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 30:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


def links(db: DB, code: str, metal: str = "XAU", now: float | None = None) -> dict:
    """How strongly a market moves with the metal (same hour, last 30 days) and whether it moves FIRST
    (its 15-minute move against the metal's next 15 minutes, last 10 days)."""
    now = time.time() if now is None else now
    out = {}
    g1, x1 = (_rets(candles.closed(db, s, "1h", now, limit=720)) for s in (metal, code))
    common = sorted(set(g1) & set(x1))
    out["corr_1h"] = _corr([x1[t] for t in common], [g1[t] for t in common])
    out["n_1h"] = len(common)
    g15, x15 = (_rets(candles.closed(db, s, "15m", now, limit=960)) for s in (metal, code))
    pairs = [(x15[t], g15[t + 900]) for t in x15 if t + 900 in g15]
    out["lead_15m"] = _corr([p[0] for p in pairs], [p[1] for p in pairs])
    out["n_15m"] = len(pairs)
    return out


def link(gold: list[float], other: list[float]) -> float | None:
    """Same-candle correlation of returns over the last 100 aligned candles (past only)."""
    g = [math.log(b / a) for a, b in zip(gold, gold[1:]) if a > 0 and b > 0][-100:]
    x = [math.log(b / a) for a, b in zip(other, other[1:]) if a > 0 and b > 0][-100:]
    n = min(len(g), len(x))
    return _corr(x[-n:], g[-n:]) if n >= 40 else None


def impulse_view(gold: list[float], other: list[float], name: str) -> tuple[float, str]:
    """Catch-up after a move in a linked market. From the last 100 aligned candles: how much the metal usually moves
    with this market in the same candle (beta). If the market just moved and the metal has not followed yet, the
    gap is expected to close in the next candle. No view without a clear link (|corr| < 0.2) or a small gap."""
    g = [math.log(b / a) for a, b in zip(gold, gold[1:]) if a > 0 and b > 0]
    x = [math.log(b / a) for a, b in zip(other, other[1:]) if a > 0 and b > 0]
    n = min(len(g), len(x))
    if n < 40:
        return 0.5, f"{name}: şam azdır"
    g, x = g[-100:], x[-100:]
    n = min(len(g), len(x))
    g, x = g[-n:], x[-n:]
    mx, mg = sum(x) / n, sum(g) / n
    sxx = sum((v - mx) ** 2 for v in x)
    sgg = sum((v - mg) ** 2 for v in g)
    if sxx <= 0 or sgg <= 0:
        return 0.5, f"{name}: hərəkət yoxdur"
    cov = sum((a - mx) * (b - mg) for a, b in zip(x, g))
    corr = cov / math.sqrt(sxx * sgg)
    if abs(corr) < 0.2:
        return 0.5, f"{name}: əlaqə zəifdir ({corr:+.2f})"
    beta = cov / sxx
    gap = beta * x[-1] - g[-1]            # what the metal should have moved minus what it did
    z = gap / math.sqrt(sgg / n)
    if abs(z) < 0.5:
        return 0.5, f"{name}: qızıl artıq reaksiya verib (əlaqə {corr:+.2f})"
    p = 0.5 * (1 + math.erf(0.25 * z / math.sqrt(2)))       # P = Phi(0.25 z), the same gentle scale as momentum
    p = min(max(p, 0.35), 0.65)
    return round(p, 4), (f"{name} son şamda {x[-1] * 100:+.3f} %, qızıl {g[-1] * 100:+.3f} %; əlaqə {corr:+.2f}: "
                         f"qızılın {'yuxarı' if gap > 0 else 'aşağı'} yetişməsi gözlənilir")
