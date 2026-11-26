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
    "USDCNH": {"name": "USD/CNH (yuan)", "epics": ["USDCNH"], "search": "USD/CNH",
               "why": "Yuan zəifləyəndə Çin alıcıları qızılla qorunur (Çin dünyanın ən böyük fiziki alıcısıdır).",
               "sign": +1},
    "COPPER": {"name": "Mis", "epics": ["COPPER", "HG", "XCUUSD"], "search": "copper",
               "why": "Mis/qızıl nisbəti iqtisadi böyümənin göstəricisidir: qalxanda sənaye metalları (gümüş, platin, "
                      "palladium) güclənir, qızıl sığınacaq kimi zəifləyir.", "sign": 0},
    # The broker has the 10-year Treasury note FUTURE (a price), not the yield: the price falls when the yield rises.
    "US10Y": {"name": "ABŞ 10 illik istiqraz (qiymət)", "epics": ["US10Y", "TNOTE", "UST10Y", "T-NOTE"],
              "search": "10-year",
              "why": "Faiz qalxanda bu istiqrazın qiyməti düşür və qızıl saxlamağın «itirilmiş gəliri» artır: "
                     "istiqraz qiyməti qalxanda (faiz enəndə) qızıl üçün adətən müsbətdir.", "sign": +1},
}
HISTORY_TF = {"15m": 4000, "30m": 4000, "1h": 4000, "4h": 3000, "1d": 2000}   # the same depth as the metals
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


