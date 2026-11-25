"""Bloklar — the organs of the system (owner 2026-11-25: «one body; each part does its own job; no duplicates»).

Every analysis method belongs to exactly ONE block (forecast.FAMILY is this map), and each block reaches the forecasts
as one voice in the consensus and is counted once in the Judge's multiple-testing bar. A block has: what it reads,
its methods (each measured by the Judge on its own), its AI analyst, the evidence it rests on, and what is still
missing (data we do not have). The support organs (Judge, learning, risk and decision) give no direction.

The block voice shown here is the same rule the consensus uses: the average lean of the block's methods that have a
view right now. Nothing here changes a forecast; it describes what the system does."""
from __future__ import annotations

import time

from .db import DB

BLOCKS = [
    {"id": "ta", "name": "Texniki analiz", "page": "/ta",
     "reads": "Şamlar (1 saat, 4 saat, 1 gün), tik həcmi, COMEX fyuçers həcmi (gündəlik)",
     "methods": ["qaydalar", "chartist", "tsmom", "trendmix"], "ai": "Qrafik analitiki (Claude Haiku)",
     "evidence": "12 növ, 34 qayda (Bilik kitabı). Güclü sübut yalnız uzun trendə aiddir (Moskowitz-Ooi-Pedersen 2012, "
                 "Hurst-Ooi-Pedersen); qısa qaydaların sübutu zəifdir — Hakim hər birini ayrıca ölçür.",
     "missing": "Order flow (hər əməliyyat): pullu Databento paketi tələb edir."},
    {"id": "fund", "name": "Fundamental", "page": "/fundamental",
     "reads": "FRED (real faiz, dollar, inflyasiya gözləntisi, VIX), ABŞ rəqəmləri (təqvim + Rəqəm ovçusu), CFTC COT, "
              "ALFRED (ilk dərc olunan rəqəm), AMFI (Hindistanın qızıl ETF axını, aylıq, rəsmi)",
     "methods": ["fundamental", "surprise"], "ai": "Strateq (Claude Sonnet) — fundamental şərh", 
     "evidence": "Dünya Qızıl Şurasının GRAM modeli: fürsət xərci (real faiz, dollar), risk, iqtisadi böyümə, mərkəzi "
                 "bank tələbi. Fed sürprizləri qızılı dəqiqələr içində tərpədir (Awartani-Hussain-Virk 2024); ABŞ "
                 "rəqəmi dəqiqəsində impuls bizim fyuçers sınağında 63,5 % (H13).",
     "missing": "Hindistanın gündəlik rəsmi qiyməti (IBJA pullu API): indilik həftəlik xəbər rəqəmləri (Bazar müxbiri)."},
    {"id": "news", "name": "Xəbər", "page": "/xeber",
     "reads": "RSS və Benzinga başlıqları, Kəşfiyyatçı (Grok, X), Hadisə birləşdiricisi (eyni xəbər bir dəfə)",
     "methods": ["xeber"], "ai": "Oxuyucu (Claude Haiku) — hər başlığı qiymətləndirir",
     "evidence": "Xəbər əhvalı qızılın gəlirinə və dəyişkənliyinə təsir edir, mənfi xəbər daha güclü (Smales 2014, 2015; "
                 "Apergis-Hayat-Saeed 2021: geopolitik xəbər daha güclü).",
     "missing": "Geopolitik risk indeksi (Caldara-Iacoviello GPR): mənbəyə hələ qoşulmayıb."},
    {"id": "cross", "name": "Bazarlar arası", "page": "/bazarlar",
     "reads": "Broker: DXY, EUR/USD, USD/JPY, USD/CNH, WTI, Brent, S&P 500, VIX, 10 illik istiqraz, mis; cüt metal",
     "methods": ["bazarlar"], "ai": None,
     "evidence": "Bazarlar arası analiz (J. Murphy); dollar qızılın ən güclü qısa müddətli amillərindən biridir; qızıl "
                 "səhm böhranlarında sığınacaqdır (Baur-Lucey 2010, Baur-McDermott 2010); neft inflyasiya kanalıdır; "
                 "mis/qızıl nisbəti böyümə göstəricisidir. 11 qayda Hakimdə ayrıca ölçülür. Metal nisbəti (IM-RATIO-1) "
                 "səhifədə göstərilir, səsi texniki analiz blokundadır.",
     "missing": "10 illik istiqrazın canlı qiyməti axşamlar kəsilir."},
    {"id": "time", "name": "Vaxt və təqvim", "page": "/vaxt",
     "reads": "Saat (UTC, London, New York), həftənin günü, ay dönüşü, ABŞ birja bayramları, ABŞ rəqəmi saatları; "
              "Hindistan/Çin zərgərlik mövsümləri",
     "methods": ["vaxt", "season", "jewel"], "ai": None,
     "evidence": "Asiya saatlarında qalxma, ABŞ saatlarında enmə (Blose və b. 2018; WGC 2024); London fiksinqi "
                 "(Caminschi-Heaney 2014); bazar ertəsi effekti (Lucey-Tully 2006); ay dönüşü və bayram ərəfəsi "
                 "(səhmlərdə güclü, qızılda zəif); ABŞ rəqəmi saatında davam (bizim H13). 7 qayda Hakimdə ayrıca ölçülür; "
                 "aylıq mövsümilik və zərgərlik mövsümü həftə-ay üfüqünün üsullarıdır.",
     "missing": "FOMC iclas təqvimi (Fed saytı) hələ qoşulmayıb: ABŞ rəqəmi saatı qaydası 14:00-ı böyük şamla tutur."},
    {"id": "brain", "name": "AI beyinlər (hamısını oxuyan)", "page": "/agents",
     "reads": "Bütün blokların faktları, Bilik kitabı",
     "methods": ["strateq", "brain2", "debate"], "ai": "Strateq (Claude), İkinci beyin (OpenAI), Müzakirə",
     "evidence": "LLM-lərin xəbərdən gəlir proqnozu (Lopez-Lira & Tang 2023); bizdə qeyd yalnız bir neçə gündür.",
     "missing": "Sahibin qərarı (2026-11-25): 4–5 gün işləsin, sonra xərc və fayda müqayisə olunacaq."},
]
SUPPORT = [
    {"id": "judge", "name": "Hakim", "does": "Hər proqnozu sonradan yoxlayır, tam xərcdən sonra pul sınağı, Holm düzəlişi, "
                                            "hipotezlər, kölgə ticarəti, etibar işıqları."},
    {"id": "learn", "name": "Öyrənmə", "does": "Vahid proqnoz (çəkilər keçmişdən), Tərəzi, konsensus, gecə yuxusu (dərslər), "
                                              "qayda təklifləri."},
    {"id": "risk", "name": "Risk və qərar", "does": "Likvidlik, risk qapısı (ABŞ rəqəmi ərəfəsi, nazik bazar), AL / SAT / GÖZLƏ."},
]
COMBINERS = ("rw", "up", "consensus", "terazi", "vahid", "garch", "gvz")


def block_of(method: str) -> str | None:
    for b in BLOCKS:
        if method in b["methods"]:
            return b["id"]
    return None


def status(db: DB, sym: str, horizon: str) -> dict:
    """Each block's voice now on one desk (the consensus rule: the average lean of its methods with a view), its
    methods' current views and the Judge's record of each."""
    from . import forecast, judge
    row = db.execute("SELECT MAX(issued_t) t FROM forecasts WHERE symbol=? AND horizon=? AND mode='live'",
                     (sym, horizon)).fetchone()
    views = {}
    if row and row["t"] is not None:
        views = {r["method"]: dict(r) for r in db.execute(
            "SELECT method, p_up, basis FROM forecasts WHERE symbol=? AND horizon=? AND mode='live' AND issued_t=?",
            (sym, horizon, row["t"])).fetchall()}
    live = {r["method"]: r for r in judge.stats(db, sym, horizon, "live", ttl=600)}
    hist = {r["method"]: r for r in judge.stats(db, sym, horizon, "history", ttl=600)}
    on_desk = set(forecast.methods_for(horizon))
    out = []
    for b in BLOCKS:
        ms = []
        for m in b["methods"]:
            if m not in on_desk:
                continue
            v = views.get(m) or {}
            r = live.get(m) if (live.get(m) or {}).get("nh") else hist.get(m)
            ms.append({"method": m, "name": forecast.METHOD_NAMES.get(m, m), "p": v.get("p_up"), "basis": v.get("basis"),
                       "record": None if not r else {k: r.get(k) for k in ("nh", "hit_rate", "bar", "status")},
                       "record_mode": "canlı" if (live.get(m) or {}).get("nh") else "tarixçə"})
        leans = [x["p"] - 0.5 for x in ms if x["p"] is not None and abs(x["p"] - 0.5) >= 0.01]
        voice = None if not leans else round(0.5 + sum(leans) / len(leans), 4)
        out.append({**{k: b[k] for k in ("id", "name", "page", "reads", "ai", "evidence", "missing")},
                    "methods": ms, "voice": voice, "with_view": len(leans), "on_desk": len(ms)})
    import json as _json
    from . import rigor
    try:
        abl = (_json.loads(db.get("unified:ablation") or "{}").get("desks") or {}).get(horizon) if sym == "XAU" else None
    except ValueError:
        abl = None
    for b in out:
        b["value"] = (abl or {}).get("without", {}).get(b["id"])
    comb = {m: {"name": forecast.METHOD_NAMES.get(m, m), "p": (views.get(m) or {}).get("p_up"),
                "basis": (views.get(m) or {}).get("basis")} for m in ("consensus", "terazi", "vahid") if m in views}
    return {"symbol": sym, "horizon": horizon, "issued_t": row["t"] if row else None, "ts": time.time(),
            "blocks": out, "combiners": comb, "support": SUPPORT, "ablation_full": (abl or {}).get("full"),
            "trials": rigor.trials(db), "finals": rigor.finals(db)}
