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


# Əsas hədəflər (Block 18, owner's focus 2026-11-24): a SECOND small family, registered later with its own time and
# bar, judged net of the FULL cost (spread + slippage + overnight financing). The first family is left as registered.
FOCUS_REGISTERED = 1795521600      # 2026-11-24 12:00 UTC (registered 08:30 UTC the same day, before any count)
FOCUS_P_BAR = 0.05 / 5
FOCUS = [
    {"id": "H9", "name": "Qızıl, 1 gün: tərəzi", "method": "terazi", "horizon": "1d", "symbol": "XAU",
     "idea": "Hakimin çəkdiyi analitiklərin birləşmiş fikri, sahibin əsas hədəfi olan gün üfüqündə.",
     "source": "sahibin fokusu; ansambl araşdırmaları"},
    {"id": "H10", "name": "Qızıl, 1 həftə: çox sürətli trend", "method": "trendmix", "horizon": "1w", "symbol": "XAU",
     "idea": "1 həftədən 1 aya qədər trendlərin dəyişkənliyə görə çəkili qarışığı.",
     "source": "Moskowitz-Ooi-Pedersen; Baltas-Kosowski"},
    {"id": "H12", "name": "Qızıl, 1 gün: vahid proqnoz", "method": "vahid", "horizon": "1d", "symbol": "XAU",
     "idea": "Sahibə göstərilən son söz: bütün analitiklər bir ehtimalda, çəkiləri sistemin öz keçmişindən öyrənilib "
             "(əlavə: 2026-11-24 10:30 UTC, qeyd vaxtından əvvəl).",
     "source": "sahibin «vahid proqnoz» tələbi; ansambl öyrənməsi"},
    {"id": "H13", "name": "Qızıl: ABŞ rəqəmi dəqiqəsində impuls, 60 dəqiqə", "kind": "news_impulse",
     "idea": "08:30, 10:00, 14:00 NY dəqiqəsində böyük hərəkət olanda 1 dəqiqə gec girib 60 dəqiqə saxlamaq. Databento "
             "2 illik sınağında: 104 halda 63,5 % davam, iki ildə də müsbət (amma sərt hədd keçilmədi). Əlavə: "
             "2026-11-24 11:20 UTC, qeyd vaxtından əvvəl.",
     "source": "öz fyuçers sınağımız (futstudy); Smales-Yang; elan sonrası sürüşmə araşdırmaları"},
    {"id": "H11", "name": "Platin və palladium impulsu (15 dəqiqə)", "kind": "impulse",
     "idea": "Böyük oyunçu tərpədəndən 1 dəqiqə sonra hərəkət 15 dəqiqə davam edir (sahibin fikri; ilk 2 gündə "
             "67-83 %, amma spreddən sonra mənfi idi).", "source": "sahibin fikri; öz impuls araşdırmamız"},
]


def _verdict(n_eff: float, hits_eff: float, bar: float, net: float | None, n: int, need: int,
             p_bar: float = P_BAR) -> tuple[float | None, str]:
    if n < need:
        return None, "az"
    p = judge._p_one_sided(round(hits_eff), round(n_eff), bar)
    if p < p_bar and (net is None or net > 0):
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
        # registered 2026-11-24 with the spread as the cost: kept as registered (full_cost came later)
        net = sum(((r["price1"] / r["price0"] - 1) * (1 if r["p_up"] > 0.5 else -1)) - judge.COST.get(r["symbol"], 0)
                  for r in rows) / n
        metals = 1 if h.get("symbol") else 4
        n_eff, hits_eff = n / k / math.sqrt(metals), hits / k / math.sqrt(metals)   # 4 metals: partly one test
        p, st = _verdict(n_eff, hits_eff, bar, net, n, 30 * k)
        row.update({"n": n, "hit_rate": hits / n, "bar": bar, "net_avg": net, "p": p, "status": st})
        out.append(row)
    return out


def _method_row(db: DB, h: dict, registered: float, p_bar: float, cost_of) -> dict:
    row = {k: h[k] for k in ("id", "name", "idea", "source")}
    tf, k = HORIZON_SPEC[h["horizon"]]
    sql = ("SELECT symbol, price0, price1, p_up FROM forecasts WHERE mode='live' AND method=? AND horizon=? "
           "AND issued_t >= ? AND price1 IS NOT NULL AND p_up != 0.5")
    args: list = [h["method"], h["horizon"], registered]
    if h.get("symbol"):
        sql += " AND symbol=?"
        args.append(h["symbol"])
    rows = db.execute(sql, args).fetchall()
    n = len(rows)
    if not n:
        row.update({"n": 0, "hit_rate": None, "bar": None, "net_avg": None, "p": None, "status": "az"})
        return row
    hits = sum((r["price1"] > r["price0"]) == (r["p_up"] > 0.5) for r in rows)
    ups = sum(r["price1"] > r["price0"] for r in rows) / n
    bar = max(0.5, ups, 1 - ups)
    net = sum(((r["price1"] / r["price0"] - 1) * (1 if r["p_up"] > 0.5 else -1)) - cost_of(r["symbol"], h["horizon"])
              for r in rows) / n
    metals = 1 if h.get("symbol") else 4
    n_eff, hits_eff = n / k / math.sqrt(metals), hits / k / math.sqrt(metals)
    p, st = _verdict(n_eff, hits_eff, bar, net, n, 30 * k, p_bar)
    row.update({"n": n, "hit_rate": hits / n, "bar": bar, "net_avg": net, "p": p, "status": st})
    return row


CLOSED = {"H6": "bağlandı: platin və palladiumun xərci (audit 2026-11-24)",
          "H11": "bağlandı: platin və palladiumun xərci; fyuçersdə də 45–47 % (audit 2026-11-24)"}


def _close(rows: list[dict]) -> list[dict]:
    for r in rows:
        if r["id"] in CLOSED:
            r["status"] = "bağlandı"
            r["idea"] = r["idea"] + " — " + CLOSED[r["id"]]
    return rows


def evaluate_focus(db: DB, now: float | None = None) -> list[dict]:
    """The owner's focus targets, judged on live results after FOCUS_REGISTERED, net of the full cost."""
    from . import impulse
    now = time.time() if now is None else now
    out = []
    for h in FOCUS:
        if h.get("kind") == "news_impulse":
            from datetime import datetime
            from zoneinfo import ZoneInfo
            row = {k: h[k] for k in ("id", "name", "idea", "source")}
            db.script("CREATE TABLE IF NOT EXISTS focus_news_impulse (t INTEGER PRIMARY KEY, cont INTEGER, net REAL)")
            ny = ZoneInfo("America/New_York")
            db.executemany("INSERT OR IGNORE INTO focus_news_impulse VALUES(?,?,?)",
                           [(e["t"], e["cont"], e["net"]) for e in impulse.events(db, now)
                            if e["t"] >= FOCUS_REGISTERED and e["symbol"] == "XAU" and e["K"] == 4.0 and e["H"] == 60
                            and (datetime.fromtimestamp(e["t"], ny).hour, datetime.fromtimestamp(e["t"], ny).minute)
                            in ((8, 30), (10, 0), (14, 0))])
            evs = [dict(r) for r in db.execute("SELECT cont, net FROM focus_news_impulse").fetchall()]
            n = len(evs)
            hits = sum(e["cont"] for e in evs)
            net = sum(e["net"] for e in evs) / n if n else None
            p, st = _verdict(n, hits, 0.5, net, n, 30, FOCUS_P_BAR)
            row.update({"n": n, "hit_rate": hits / n if n else None, "bar": 0.5, "net_avg": net, "p": p, "status": st})
            out.append(row)
            continue
        if h.get("kind") == "impulse":
            row = {k: h[k] for k in ("id", "name", "idea", "source")}
            # one-minute candles are kept 30 days: each impulse is stored once when seen, so the count only grows
            db.script("CREATE TABLE IF NOT EXISTS focus_impulse (t INTEGER, symbol TEXT, cont INTEGER, net REAL, "
                      "PRIMARY KEY (t, symbol))")
            db.executemany("INSERT OR IGNORE INTO focus_impulse VALUES(?,?,?,?)",
                           [(e["t"], e["symbol"], e["cont"], e["net"]) for e in impulse.events(db, now)
                            if e["t"] >= FOCUS_REGISTERED and e["symbol"] in ("XPT", "XPD") and e["K"] == 4.0
                            and e["H"] == 15])
            evs = [dict(r) for r in db.execute("SELECT cont, net FROM focus_impulse").fetchall()]
            n = len(evs)
            hits = sum(e["cont"] for e in evs)
            net = sum(e["net"] for e in evs) / n if n else None
            p, st = _verdict(n, hits, 0.5, net, n, 60, FOCUS_P_BAR)
            row.update({"n": n, "hit_rate": hits / n if n else None, "bar": 0.5, "net_avg": net, "p": p, "status": st})
            out.append(row)
        else:
            out.append(_method_row(db, h, FOCUS_REGISTERED, FOCUS_P_BAR, judge.full_cost))
    return out


# ---------- V family (audit 2026-11-24, re-registered): what the owner needs, measured the right way ----------
# Every test is on MONEY: the average result in the forecast's direction minus the full cost (spread + slippage +
# overnight financing), one-sided t against zero, on independent cases only (overlapping forecasts thinned to one
# per horizon; several metals pooled as one portfolio per date). Gold-only where the broker's cost allows a profit;
# the four metals pooled only at long horizons, where the cost is small against the move. H1–H13 stay visible as
# the earlier registrations; H6 and H11 can never pass (platinum/palladium cost) and are closed.
V_REGISTERED = 1795543200          # 2026-11-24 18:00 UTC (registered 15:30 UTC, before any of its data)
V_P_BAR = 0.05 / 5
V_TESTS = [
    {"id": "V1", "name": "Qızıl, 1 gün: vahid proqnoz (pulla)", "method": "vahid", "horizon": "1d", "metals": ("XAU",),
     "idea": "Sahibə göstərilən son söz pul qazandırırmı? Təxmini müddət: kiçik üstünlük üçün illər; böyük üçün aylar.",
     "source": "sahibin vahid proqnoz tələbi"},
    {"id": "V2", "name": "Qızıl, 1 həftə: çox sürətli trend (pulla)", "method": "trendmix", "horizon": "1w",
     "metals": ("XAU",), "idea": "Həftəlik trend; canlı sübut uzun çəkir (həftədə 1 hal).",
     "source": "Moskowitz-Ooi-Pedersen; Baltas-Kosowski"},
    {"id": "V3", "name": "4 metal birlikdə, 1 həftə: 12 aylıq trend (portfel)", "method": "tsmom", "horizon": "1w",
     "metals": ("XAU", "XAG", "XPT", "XPD"), "idea": "Trendin ən güclü sübutu portfeldədir: hər həftə 4 metalın orta "
     "nəticəsi bir hal sayılır.", "source": "Moskowitz-Ooi-Pedersen"},
    {"id": "V4", "name": "4 metal birlikdə, 1 ay: al və saxla (portfel)", "method": "up", "horizon": "1mo",
     "metals": ("XAU", "XAG", "XPT", "XPD"), "idea": "Sadəcə saxlamaq tam xərcdən sonra qazandırırmı? Kölgə "
     "ticarətində qızıl 1 ayda ən yaxşı nəticə budur.", "source": "öz kölgə ticarətimiz; audit"},
    {"id": "V5", "name": "Qızıl: ABŞ rəqəmi dəqiqəsində impuls, 60 dəqiqə (pulla)", "kind": "news_impulse",
     "idea": "Fyuçers sınağında 63,5 % davam (104 hal). Ildə ~50 hal: qərar üçün təxminən 1–2 il.",
     "source": "öz fyuçers sınağımız"},
]


def _t_p(xs: list[float]) -> tuple[float | None, float | None]:
    n = len(xs)
    if n < 2:
        return (sum(xs) / n if n else None), None
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1)) or 1e-12
    t = mu / (sd / math.sqrt(n))
    return mu, 1 - 0.5 * (1 + math.erf(t / math.sqrt(2)))


def evaluate_v(db: DB, now: float | None = None) -> list[dict]:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from . import impulse
    now = time.time() if now is None else now
    out = []
    for h in V_TESTS:
        row = {k: h[k] for k in ("id", "name", "idea", "source")}
        if h.get("kind") == "news_impulse":
            ny = ZoneInfo("America/New_York")
            db.script("CREATE TABLE IF NOT EXISTS v_news_impulse (t INTEGER PRIMARY KEY, cont INTEGER, net REAL)")
            db.executemany("INSERT OR IGNORE INTO v_news_impulse VALUES(?,?,?)",
                           [(e["t"], e["cont"], e["net"]) for e in impulse.events(db, now)
                            if e["t"] >= V_REGISTERED and e["symbol"] == "XAU" and e["K"] == 4.0 and e["H"] == 60
                            and (datetime.fromtimestamp(e["t"], ny).hour, datetime.fromtimestamp(e["t"], ny).minute)
                            in ((8, 30), (10, 0), (14, 0))])
            evs = [dict(r) for r in db.execute("SELECT cont, net FROM v_news_impulse").fetchall()]
            cases = [e["net"] for e in evs]
            hits = sum(e["cont"] for e in evs)
            nk = len(evs)
        else:
            _, k = HORIZON_SPEC[h["horizon"]]
            ph = ",".join("?" * len(h["metals"]))
            rows = db.execute(f"SELECT symbol, issued_t, price0, price1, p_up FROM forecasts WHERE mode='live' AND "
                              f"method=? AND horizon=? AND symbol IN ({ph}) AND issued_t >= ? AND price1 IS NOT NULL "
                              f"AND p_up != 0.5 ORDER BY issued_t",
                              (h["method"], h["horizon"], *h["metals"], V_REGISTERED)).fetchall()
            dates = sorted({r["issued_t"] for r in rows})[::k]      # one case per horizon: no overlap
            keep = set(dates)
            by: dict[int, list] = {}
            hits = nk = 0
            for r in rows:
                if r["issued_t"] not in keep or not r["price0"]:
                    continue
                d = 1 if r["p_up"] > 0.5 else -1
                ret = (r["price1"] / r["price0"] - 1) * d
                hits += int(ret > 0)
                nk += 1
                by.setdefault(r["issued_t"], []).append(ret - judge.full_cost(r["symbol"], h["horizon"]))
            cases = [sum(v) / len(v) for _, v in sorted(by.items())]   # several metals = one portfolio per date
        mu, p = _t_p(cases)
        n = len(cases)
        status = "az" if n < 30 else ("sübut" if p is not None and p < V_P_BAR and mu > 0 else "yox")
        row.update({"n": n, "hit_rate": hits / nk if nk else None, "net_avg": mu, "p": p, "status": status,
                    "bar": None})
        out.append(row)
    return out
