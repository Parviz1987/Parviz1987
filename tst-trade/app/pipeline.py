"""The whole chain, link by link: from a price or a headline arriving to the Judge's verdict on the card.

Each link says whether it works now (ok / warn / bad / closed), with the number that shows it, and what it feeds.
A link that stops is visible at once, also when nothing raises an error (a quiet stall: headlines no longer labelled,
a release with no figure, forecasts not scored). Consistency checks catch links that contradict each other
(a source clock far from ours, a price jump that is a bad tick, a method whose input never arrives)."""
from __future__ import annotations

import json
import time

from . import brains, candles, forecast, markets
from .db import DB


RELATED_SILENT = 3600      # a linked market silent for an hour while metals trade: really missing


def _row(stage, feeds_into, status, msg, n=None):
    return {"stage": stage, "into": feeds_into, "status": status, "msg": msg, "n": n}


def check(db: DB, keys, engine, feeds, jobs, now: float | None = None) -> list[dict]:
    from .engine import market_open
    now = time.time() if now is None else now
    open_ = market_open(now)
    out = []

    # 1. prices
    live = [s for s in candles.METALS if engine.status(s, now) in ("LIVE", "DEMO")]
    if not open_:
        out.append(_row("Qiymət axını (4 metal)", "şamlar", "closed", "bazar bağlıdır"))
    else:
        out.append(_row("Qiymət axını (4 metal)", "şamlar", "ok" if len(live) == 4 else "bad" if not live else "warn",
                        f"{len(live)}/4 canlı", len(live)))
    epics = markets.saved(db).get("epics", {})
    # The stream sends a price only when it changes: a quiet market at night (or one closed for its own hours,
    # e.g. Brent before the London open) is silent for minutes without anything being wrong. Missing = nothing for
    # RELATED_SILENT while the metals trade.
    ages = {c: now - engine.quotes[c]["recv_ts"] if c in engine.quotes else None for c in epics}
    def last_candle(c):
        r = db.execute("SELECT MAX(t) m FROM candles WHERE symbol=? AND tf='15m'", (c,)).fetchone()
        return r["m"] if r and r["m"] else None
    for c, a in list(ages.items()):
        if a is None or a > RELATED_SILENT:        # nothing streamed: the broker's own bars may still be fresh
            lc = last_candle(c)
            if lc and now - lc < 2 * RELATED_SILENT:
                ages[c] = min(a if a is not None else 1e9, RELATED_SILENT)
    missing = [c for c, a in ages.items() if a is None or a > RELATED_SILENT]
    quiet = [c for c, a in ages.items() if a is not None and 120 < a <= RELATED_SILENT]
    if open_ and epics:
        msg = f"{len(epics) - len(missing)}/{len(epics)} gəlir"
        if quiet:
            msg += "; sakit (qiymət az dəyişir): " + ", ".join(
                f"{markets.RELATED[c]['name']} {ages[c] / 60:.0f} dəq" for c in quiet)
        if missing:
            msg += "; gəlməyən: " + ", ".join(markets.RELATED[c]["name"] for c in missing)
        out.append(_row("Əlaqəli bazarlar (dollar, neft...)", "dollar/neft impulsu, «Bazarlar»",
                        "ok" if not missing else "warn", msg, len(epics) - len(missing)))
    # source clock against ours (a source far behind or ahead makes LIVE a lie)
    skews = [abs(q["recv_ts"] - q["source_ts"]) for s, q in engine.quotes.items()
             if s in candles.METALS and not q.get("ts_missing") and now - q["recv_ts"] < 120]
    if skews:
        sk = sorted(skews)[len(skews) // 2]
        out.append(_row("Mənbə saatı ilə bizim saat", "LIVE / DELAYED nişanı", "ok" if sk < 30 else "warn",
                        f"fərq {sk:.1f} san", round(sk, 1)))

    # 2. candles: a fresh 15-minute candle for each metal; and no bad tick (a >3 % jump inside one minute)
    if open_:
        fresh = [s for s in candles.METALS
                 if (candles.get(db, s, "15m", limit=1) or [{"t": 0}])[-1]["t"] > now - 1800]
        out.append(_row("Şamlar (15 dəq)", "proqnoz masaları", "ok" if len(fresh) == 4 else "warn",
                        f"{len(fresh)}/4 metalda son 30 dəqiqədə şam var", len(fresh)))
    jumps = db.execute("SELECT COUNT(*) FROM candles WHERE tf='1m' AND t > ? AND symbol IN ('XAU','XAG','XPT','XPD') "
                       "AND l > 0 AND (h - l) / l > 0.03", (now - 86400,)).fetchone()[0]
    out.append(_row("Səhv tik yoxlaması", "şamlar", "ok" if not jumps else "warn",
                    "son gündə 1 dəqiqədə 3 %-dən böyük sıçrayış yoxdur" if not jumps else
                    f"{jumps} dəqiqəlik şamda 3 %-dən böyük sıçrayış: mənbəni yoxlayın", jumps))

    # 3. news in, 4. news -> Reader
    n1h = db.execute("SELECT COUNT(*) FROM news WHERE ts > ?", (now - 3600,)).fetchone()[0]
    out.append(_row("Xəbər mənbələri (RSS, Benzinga, Grok)", "Oxuyucu", "ok" if n1h else "warn",
                    f"son 1 saatda {n1h} başlıq", n1h))
    try:
        stuck = db.execute("SELECT COUNT(*) FROM news n LEFT JOIN news_ai a ON a.uid=n.uid WHERE a.uid IS NULL "
                           "AND n.ts BETWEEN ? AND ?", (now - 6 * 3600, now - 900)).fetchone()[0]
    except Exception:
        stuck = 0
    labelled = db.execute("SELECT COUNT(*) FROM news_ai WHERE ts > ?", (now - 3600,)).fetchone()[0]
    out.append(_row("Oxuyucu (başlıqları qiymətləndirir)", "Xəbər əhvalı üsulu, Strateq",
                    "ok" if stuck < 10 else "warn",
                    f"son 1 saatda {labelled} qiymətləndirmə; 15 dəqiqədən çox gözləyən {stuck}", stuck))

    # 5. scout
    sc = jobs.last_scout()
    age = (now - sc["ts"]) / 3600 if sc else None
    out.append(_row("Kəşfiyyatçı (Grok, X)", "xəbər siyahısı", "closed" if not open_ else
                    "ok" if age is not None and age < 9 else "warn",
                    "hələ axtarmayıb" if age is None else f"son axtarış {age:.1f} saat əvvəl", None))

    # 6. calendar -> hunter -> 7. surprise
    since = float(db.get("hunter:since") or now)   # releases before the hunter existed are not its misses
    try:
        missed = db.execute(
            "SELECT COUNT(*) FROM events e WHERE e.country='USD' AND e.impact IN ('High','Medium') AND e.forecast IS "
            "NOT NULL AND e.ts BETWEEN ? AND ? AND NOT EXISTS (SELECT 1 FROM hunter_log h WHERE h.event=e.title "
            "AND h.accepted=1 AND h.ts > e.ts)", (max(now - 86400, since), now - 1500)).fetchone()[0]
        found = db.execute("SELECT COUNT(*) FROM hunter_log WHERE accepted=1 AND ts > ?", (now - 86400,)).fetchone()[0]
    except Exception:
        missed, found = 0, 0
    out.append(_row("Rəqəm ovçusu (ABŞ rəqəmləri)", "Hadisə sürprizi üsulu",
                    "ok" if not missed else "warn",
                    f"son gündə {found} rəqəm təsdiqləndi; tapılmayan {missed}", missed))

    # 8. forecasts issued per horizon (a desk that stopped issuing is a broken link)
    if open_:
        late = []
        for h, tf in forecast.HORIZONS.items():
            if tf not in ("15m", "30m", "1h", "4h"):
                continue
            t = db.execute("SELECT MAX(issued_t) t FROM forecasts WHERE horizon=? AND mode='live'", (h,)).fetchone()["t"]
            if t is None or now - t > 2.5 * candles.TF[tf]:
                late.append(forecast.HORIZON_NAMES[h])
        out.append(_row("Proqnoz masaları (15 dəq – 4 saat)", "Hakim", "ok" if not late else "warn",
                        "hamısı vaxtında" if not late else "gecikir: " + ", ".join(late), len(late)))
    # 9. Judge: overdue intraday forecasts not scored
    overdue = db.execute("SELECT COUNT(*) FROM forecasts WHERE scored_ts IS NULL AND horizon IN ('15m','30m','1h','4h') "
                         "AND target_t < ?", (now - 3 * 3600,)).fetchone()[0]
    out.append(_row("Hakim (proqnozları yoxlayır)", "kartlar, dəqiqlik qrafikləri",
                    "ok" if overdue < 50 else "warn", f"vaxtı keçib yoxlanmayan {overdue}", overdue))

    # 10. inputs of the methods: a method whose input never arrives is a dead link
    dead = []
    for m, label in (("dollar", "Dollar impulsu"), ("oil", "Neft impulsu"), ("news", "Xəbər əhvalı"),
                     ("strateq", "Strateqin fikri"), ("surprise", "Hadisə sürprizi"), ("macro", "Makro")):
        r = db.execute("SELECT COUNT(*) n, SUM(p_up != 0.5) v FROM forecasts WHERE method=? AND mode='live' "
                       "AND issued_t > ?", (m, now - 86400)).fetchone()
        if r["n"] and not r["v"]:
            # why: the method's own words on its latest forecast ("no candles", "weak link"...)
            why = db.execute("SELECT basis FROM forecasts WHERE method=? AND mode='live' ORDER BY issued_t DESC "
                             "LIMIT 1", (m,)).fetchone()
            dead.append(f"{label} («{why['basis'][:70]}»)" if why else label)
    out.append(_row("Üsulların girişi", "konsensus, kartlar", "ok" if not dead else "warn",
                    "hər üsulun son gündə fikri olub" if not dead else
                    "son gündə heç fikri olmayan: " + ", ".join(dead) + " (giriş gəlmir və ya şərt yaranmayıb)",
                    len(dead)))

    # 11. brains' budget
    near = [f"{b['name']} {b['spent']:.1f}/{b['config']['month_usd']:.0f} $" for b in brains.view(db, keys)
            if b["in_use"] and b["spent"] >= 0.8 * float(b["config"]["month_usd"])]
    out.append(_row("Beyinlərin aylıq limiti", "bütün beyin işləri", "ok" if not near else "warn",
                    "hamısı limitin 80 %-dən aşağıdır" if not near else "limitə yaxın: " + "; ".join(near), len(near)))
    return out


def summary(rows: list[dict]) -> dict:
    return {"ok": sum(r["status"] == "ok" for r in rows), "warn": [r["stage"] for r in rows if r["status"] == "warn"],
            "bad": [r["stage"] for r in rows if r["status"] == "bad"]}


def as_json(rows) -> str:
    return json.dumps(rows, ensure_ascii=False)
