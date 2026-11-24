"""Əsas fərziyyələr (pre-registered hypotheses, Block 8): a short list fixed IN ADVANCE, judged only on live forecasts
issued after the registration time — so nothing here was chosen by looking at the data it is judged on.

Why: the Judge tests ~480 method/desk pairs at once; to prove a 53 % hit rate at that strictness takes ~5,700
independent forecasts. A small family (8) chosen beforehand from the research needs far fewer, and stays honest:
the bar is 0.05 / 8, the forecasts are new, overlapping forecasts count as n / k, and a result must also pay after the
spread. Each hypothesis says where its idea comes from. Changing this list means a new registration time."""
from __future__ import annotations

import math
import time

from . import brainviews, judge
from .db import DB
from .forecast import HORIZON_SPEC

REGISTERED = 1795521600            # 2026-11-24 12:00 UTC: only forecasts issued after this count
P_BAR = 0.05 / 8

HYPOTHESES = [
    {"id": "H1", "name": "Beyinlər həyəcandan sonra (1 saat)",
     "idea": "Güclü xəbər, ABŞ rəqəmi və ya sıçrayışdan sonra beyinlər istiqaməti deyir — cavabın gəldiyi andan, "
             "«artıq olan hərəkət davam edir» rəqibindən yaxşı.", "source": "Lopez-Lira & Tang; sinir sistemi planı",
     "kind": "brains"},
    {"id": "H2", "name": "12 aylıq trend, 4 metal birlikdə (1 həftə)", "method": "tsmom", "horizon": "1w",
     "idea": "Ən güclü sübutu olan fikir; tək metalda zəif, portfeldə ölçülür.", "source": "Moskowitz-Ooi-Pedersen"},
    {"id": "H3", "name": "12 aylıq trend, 4 metal birlikdə (1 ay)", "method": "tsmom", "horizon": "1mo",
     "idea": "Eyni fikir, ay üfüqündə.", "source": "Hurst-Ooi-Pedersen"},
    {"id": "H4", "name": "Seçici konsensus (1 gün)", "method": "consensus", "horizon": "1d",
     "idea": "Yalnız müstəqil fikir ailələri razı olanda.", "source": "ansambl araşdırmaları"},
    {"id": "H5", "name": "Tərəzi (1 saat)", "method": "terazi", "horizon": "1h",
     "idea": "Hakimin çəkisi ilə birləşmiş fikir.", "source": "ansambl və kalibrləmə"},
    {"id": "H6", "name": "Dollar impulsu (15 dəqiqə)", "method": "dollar", "horizon": "15m",
     "idea": "Dollar sıçrayanda qızıl bir neçə dəqiqə gec reaksiya verir.", "source": "qiymət kəşfi araşdırmaları"},
    {"id": "H7", "name": "ABŞ rəqəmi sürprizi (1 saat)", "method": "surprise", "horizon": "1h",
     "idea": "Rəqəm gözləntidən fərqli çıxanda reaksiya davam edir.", "source": "Elder-Miao-Ramchander; Smales-Yang"},
    {"id": "H8", "name": "Qısa dönüş, qızıl (30 dəqiqə)", "method": "reversal", "horizon": "30m", "symbol": "XAU",
     "idea": "Keçmişdə 63 % çıxıb — məlumata baxıb seçildiyi üçün yalnız YENİ canlı məlumatla sayılır.",
     "source": "öz tarixçəmiz (məlumata baxılaraq seçilib)"},
]


def _verdict(n_eff: float, hits_eff: float, bar: float, net: float | None, n: int, need: int) -> tuple[float | None, str]:
    if n < need:
        return None, "az"
    p = judge._p_one_sided(round(hits_eff), round(n_eff), bar)
    if p < P_BAR and (net is None or net > 0):
        return p, "sübut"
    return p, "yox"


def evaluate(db: DB, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    out = []
    for h in HYPOTHESES:
        row = {k: h[k] for k in ("id", "name", "idea", "source")}
        if h.get("kind") == "brains":
            cards = [c for c in brainviews.score(db, now, days=90) if c["when"] == "həyəcan" and c["horizon"] == "1h"]
            n = sum(c["n"] for c in cards)
            hits = sum(c["hit_rate"] * c["n"] for c in cards)
            base_n = sum(c["baseline_n"] for c in cards)
            bar = max(0.5, (sum((c["baseline_hit"] or 0) * c["baseline_n"] for c in cards) / base_n) if base_n else 0.5)
            net = sum(c["net_avg"] * c["n"] for c in cards) / n if n else None
            # four metals per alarm move together: about one independent test per alarm
            p, st = _verdict(n / 4, hits / 4, bar, net, n, 120)
            row.update({"n": n, "hit_rate": hits / n if n else None, "bar": bar, "net_avg": net, "p": p, "status": st})
            out.append(row)
            continue
        tf, k = HORIZON_SPEC[h["horizon"]]
        sql = ("SELECT symbol, price0, price1, p_up FROM forecasts WHERE mode='live' AND method=? AND horizon=? "
               "AND issued_t >= ? AND price1 IS NOT NULL AND p_up != 0.5")
        args: list = [h["method"], h["horizon"], REGISTERED]
        if h.get("symbol"):
            sql += " AND symbol=?"
            args.append(h["symbol"])
        rows = db.execute(sql, args).fetchall()
        n = len(rows)
        if not n:
            row.update({"n": 0, "hit_rate": None, "bar": None, "net_avg": None, "p": None, "status": "az"})
            out.append(row)
            continue
        hits = sum((r["price1"] > r["price0"]) == (r["p_up"] > 0.5) for r in rows)
        ups = sum(r["price1"] > r["price0"] for r in rows) / n
        bar = max(0.5, ups, 1 - ups)
        net = sum(((r["price1"] / r["price0"] - 1) * (1 if r["p_up"] > 0.5 else -1)) - judge.COST.get(r["symbol"], 0)
                  for r in rows) / n
        metals = 1 if h.get("symbol") else 4
        n_eff, hits_eff = n / k / math.sqrt(metals), hits / k / math.sqrt(metals)   # 4 metals: partly one test
        p, st = _verdict(n_eff, hits_eff, bar, net, n, 30 * k)
        row.update({"n": n, "hit_rate": hits / n, "bar": bar, "net_avg": net, "p": p, "status": st})
        out.append(row)
    return out
