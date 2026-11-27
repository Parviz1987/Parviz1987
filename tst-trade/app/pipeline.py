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
RANGE_ONLY = ("garch", "gvz")                  # they give the range, never a direction
NEWS_SOURCES = ("rss", "alpaca")               # zero rows from these on a trading day means nothing arrived
STALE_SOURCE = 26 * 3600                       # the slowest source is checked daily
FRESH_SHEETS = (("blocks:audit", "blokların yoxlaması", 4 * 3600),   # hourly, paused 04-05 UTC ("conductor:audit", "dirijorun sübutu", 30 * 3600),
                ("aci:shadow", "aralıq düzəlişi (ACI)", 8 * 86400))             # weekly since 27.11


def _row(stage, feeds_into, status, msg, n=None):
    return {"stage": stage, "into": feeds_into, "status": status, "msg": msg, "n": n}


def _short_day(ts: float) -> bool:
    """A day the metals do not trade, or the afternoon of a short day: the same calendar as the repair and the
    outside watcher (heartbeat.holiday / early_close), so the three never disagree about «closed»."""
    from .heartbeat import early_close, holiday
    return holiday(ts) or early_close(ts)


def release_counts(db: DB, now: float, since: float) -> tuple[int, int, int]:
    """US releases of the last day (after the 25-minute grace): how many, how many have an actual from EITHER source
    (the agency itself, «Rəsmi rəqəmlər», or the two brains), and how many the brains confirmed."""
    from . import official as off
    evs = db.execute("SELECT title, ts FROM events WHERE country='USD' AND impact IN ('High','Medium') AND forecast "
                     "IS NOT NULL AND ts BETWEEN ? AND ?", (max(now - 86400, since), now - 1500)).fetchall()
    known = sum(1 for e in evs if db.execute("SELECT 1 FROM releases WHERE uid=? AND actual IS NOT NULL",
                                             (off.uid_of(e["title"], e["ts"]),)).fetchone())
    try:
        found = db.execute("SELECT COUNT(*) FROM hunter_log WHERE accepted=1 AND ts > ?", (now - 86400,)).fetchone()[0]
    except Exception:
        found = 0
    return len(evs), known, found


def check(db: DB, keys, engine, feeds, jobs, now: float | None = None) -> list[dict]:
    from .engine import market_open
    now = time.time() if now is None else now
    open_ = market_open(now)
    out = []

    # 1. prices
    live = [s for s in candles.METALS if engine.status(s, now) in ("LIVE", "DEMO")]
    if not open_:
        out.append(_row("Qiymət axını (4 metal)", "şamlar", "closed", "bazar bağlıdır"))
    elif len(live) < 4 and _short_day(now):
        # a holiday or a short day's afternoon (the repair and the outside watcher already treat it so): quiet is
        # expected, not a broken first link
        out.append(_row("Qiymət axını (4 metal)", "şamlar", "closed", f"bayram / qısa gün: {len(live)}/4 canlı",
                        len(live)))
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
        # Block 17: only the first headline of an event is read; its copies are not «waiting» (they never will be)
        from . import newsevents
        newsevents.ensure(db)
        stuck = db.execute("SELECT COUNT(*) FROM news n LEFT JOIN news_ai a ON a.uid=n.uid "
                           "LEFT JOIN news_event e ON e.uid=n.uid WHERE a.uid IS NULL AND n.ts BETWEEN ? AND ? "
                           "AND (e.uid IS NULL OR e.uid = (SELECT e2.uid FROM news_event e2 WHERE e2.event_id=e.event_id "
                           "ORDER BY e2.ts, e2.uid LIMIT 1))", (now - 6 * 3600, now - 900)).fetchone()[0]
    except Exception:
        stuck = 0
    labelled = db.execute("SELECT COUNT(*) FROM news_ai WHERE ts > ?", (now - 3600,)).fetchone()[0]
    out.append(_row("Oxuyucu (başlıqları qiymətləndirir)", "Xəbər əhvalı üsulu, Strateq",
                    "ok" if stuck < 10 else "warn",
                    f"son 1 saatda {labelled} qiymətləndirmə; 15 dəqiqədən çox gözləyən {stuck}", stuck))

    # 5. scout
    sc = jobs.last_scout()
    age = (now - sc["ts"]) / 3600 if sc else None
    # since 27.11 it searches only around a high-impact release and on a news alarm: a long quiet is normal
    out.append(_row("Kəşfiyyatçı (Grok, X)", "xəbər siyahısı", "ok",
                    ("yalnız böyük ABŞ rəqəmi ətrafında və xəbər həyəcanında axtarır; " +
                     ("hələ axtarmayıb" if age is None else f"son axtarış {age:.1f} saat əvvəl")), None))

    # 6. calendar -> hunter -> 7. surprise
    since = float(db.get("hunter:since") or now)   # releases before the hunter existed are not its misses
    # A release counts as found when its actual is known from EITHER source: the agency itself (BLS / FRED, «Rəsmi
    # rəqəmlər») or the two brains (2026-11-26: GDP and PCE came from FRED, but only the brains were counted).
    try:
        n_ev, n_known, found = release_counts(db, now, since)
    except Exception:
        n_ev, n_known, found = 0, 0, 0
    missed = n_ev - n_known
    out.append(_row("Rəqəm ovçusu (ABŞ rəqəmləri)", "Hadisə sürprizi üsulu",
                    "ok" if not missed else "warn",
                    f"son gündə {n_ev} rəqəm: {n_known} məlum (iki beyin {found}, qalanı rəsmi mənbədən); "
                    f"tapılmayan {missed}", missed))

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
    # a target that fell while the market was closed (daily break, weekend) has no candle and is dropped after a day
    # by the Judge, never guessed: it is not «overdue». Only targets in open market hours count.
    from .engine import market_open
    overdue = sum(1 for r in db.execute("SELECT target_t FROM forecasts WHERE scored_ts IS NULL AND horizon IN "
                                        "('15m','30m','1h','4h') AND target_t < ?", (now - 3 * 3600,)).fetchall()
                  if market_open(r["target_t"] - 60)      # closed hours incl. the daily break, on New York time
                  and not _short_day(r["target_t"] - 60))  # holidays and short afternoons (seen Thanksgiving 2026)
    out.append(_row("Hakim (proqnozları yoxlayır)", "kartlar, dəqiqlik qrafikləri",
                    "ok" if overdue < 50 else "warn", f"vaxtı keçib yoxlanmayan {overdue}", overdue))

    # 10. every analyst's own voice (27.11: the old check looked at 5 of 18; the seasonal voices and the selective
    # consensus had been silent for days unseen). Dead: nothing issued for 3 days; mute: issues, but never a view
    # (always 0.5) for a week. Ranges-only methods and the benchmarks have no direction by design.
    from .blockaudit import voices, METALS_SQL
    act3, act7 = voices(db, now - 4 * 86400), voices(db, now - 7 * 86400)   # 4 days: a holiday Friday + weekend
    dead, mute = [], []
    for m in forecast.METHODS:
        if m in forecast.BASELINES or m in RANGE_ONLY:
            continue
        name = forecast.METHOD_NAMES.get(m, m).split(" (")[0]
        if not act3.get(m, {}).get("n"):
            dead.append(name)
        elif not act7.get(m, {}).get("v"):
            why = db.execute(f"SELECT basis FROM forecasts WHERE symbol IN {METALS_SQL} AND mode='live' AND "
                             "target_t > ? AND method=? ORDER BY issued_t DESC LIMIT 1", (now - 4 * 86400, m)).fetchone()
            mute.append(f"{name} («{why['basis'][:60]}»)" if why and why["basis"] else name)
    parts = (["susur (4 gündə proqnoz yoxdur): " + ", ".join(dead)] if dead else []) + \
            (["fikri yoxdur (7 gündə hamısı 0.5): " + "; ".join(mute)] if mute else [])
    out.append(_row("Üsulların səsi (hər analitik)", "vahid proqnoz, Hakim, kartlar",
                    "bad" if dead and open_ else "warn" if dead or mute else "ok",
                    "; ".join(parts) if parts else "hər analitikin son həftədə fikri olub", len(dead) + len(mute)))

    # 12. sources: an error, a check that stopped running, a partial failure hidden behind «ok», and a news source
    # that answers but brings nothing on a trading day (27.11: Alpaca «ok» with 0 headlines in 48 hours)
    from . import feeds as feeds_mod
    broken, stale, partial, empty = [], [], [], []
    for sid in feeds_mod.SOURCE_IDS:
        h = feeds.health(sid)
        if not h or h.get("ok") is None:          # never checked, or deliberately not used (shown grey elsewhere)
            continue
        if h.get("ok") is False:
            broken.append(f"{sid} ({str(h.get('message') or '')[:60]})")
        elif h.get("checked") and now - h["checked"] > STALE_SOURCE:
            stale.append(f"{sid} {(now - h['checked']) / 3600:.0f} saat")
        elif "xəta" in str(h.get("message") or "") or "limitə görə" in str(h.get("message") or ""):
            partial.append(f"{sid} ({str(h['message']).split('xəta:', 1)[-1].strip()[:70]})")
        elif sid in NEWS_SOURCES and not h.get("rows") and open_ and not _short_day(now):
            empty.append(f"{sid} ({str(h.get('message') or '')[:50]})")
    parts = (["işləmir: " + "; ".join(broken)] if broken else []) + \
            (["yoxlanmır: " + ", ".join(stale)] if stale else []) + \
            (["qismən: " + "; ".join(partial)] if partial else []) + \
            (["cavab verir, amma heç nə gətirmir: " + "; ".join(empty)] if empty else [])
    out.append(_row("Mənbələr (hər biri ayrıca)", "bloklar", "bad" if broken else "warn" if parts else "ok",
                    "; ".join(parts) if parts else f"{len(feeds_mod.SOURCE_IDS)} mənbənin hamısı qaydasındadır",
                    len(broken) + len(stale) + len(partial) + len(empty)))

    # 11. brains' budget
    near = [f"{b['name']} {b['spent']:.1f}/{b['config']['month_usd']:.0f} $" for b in brains.view(db, keys)
            if b["in_use"] and b["spent"] >= 0.8 * float(b["config"]["month_usd"])]
    out.append(_row("Beyinlərin aylıq limiti", "bütün beyin işləri", "ok" if not near else "warn",
                    "hamısı limitin 80 %-dən aşağıdır" if not near else "limitə yaxın: " + "; ".join(near), len(near)))

    # 12b. how late each news source is (plan 27.11 step 9.2): from the headline's own time to its arrival here,
    # median of the last day; and how fast the last US figure came from the agency at its minute (the sniper)
    try:
        lat: dict[str, list[float]] = {}
        for r in db.execute("SELECT source, received_ts - ts d FROM news WHERE received_ts IS NOT NULL AND received_ts > ? "
                            "AND ts > ?", (now - 86400, now - 2 * 86400)).fetchall():
            if r["d"] is not None and r["d"] >= 0:
                lat.setdefault(r["source"], []).append(r["d"])
        parts = [f"{s}: {sorted(v)[len(v) // 2] / 60:.0f} dəq ({len(v)})" for s, v in sorted(lat.items(), key=lambda x: -len(x[1]))[:6]]
        od = json.loads(db.get("official:last_delay") or "null")
        if od:
            parts.append(f"son ABŞ rəqəmi ({od['event']}): {od['seconds']:.0f} san sonra")
        out.append(_row("Xəbər gecikməsi (mənbə-mənbə)", "həyəcan, Oxuyucu", "ok",
                        "; ".join(parts) if parts else "hələ ölçü yoxdur (gəliş vaxtı 27.11-dən yazılır)", None))
    except Exception:
        pass

    # 13. brains answering: per job, the share of calls that worked in the last day (a fallback that fails, an answer
    # cut off) and models the provider has closed
    try:          # a job = the calls of one slot within 2 minutes (a failed primary + a working fallback = answered)
        weak = [f"{r['slot']} {r['good']}/{r['jobs']}" for r in db.execute(
            "SELECT slot, COUNT(*) jobs, SUM(okb) good FROM (SELECT slot, CAST(ts / 120 AS INTEGER) b, MAX(ok) okb "
            "FROM brain_calls WHERE ts > ? GROUP BY slot, b) GROUP BY slot", (now - 86400,)).fetchall()
            if r["jobs"] >= 5 and r["good"] < 0.8 * r["jobs"]]
    except Exception:
        weak = []
    try:          # a closed model counts only while a brain is still set to use it (replaced ones are history)
        used = set()
        for b in brains.view(db, keys):
            c = b["config"]
            used |= {(c.get("provider"), c.get("model")), (c.get("fallback"), c.get("fallback_model"))}
        closed = [f"{r['provider']} {r['model']}" for r in db.execute("SELECT provider, model FROM llm_state WHERE off "
                                                                      "IS NOT NULL AND off != ''").fetchall()
                  if (r["provider"], r["model"]) in used]
    except Exception:
        closed = []
    parts = (["24 saatda cavab alınan iş 80 %-dən az: " + ", ".join(weak)] if weak else []) + \
            (["söndürülmüş model (iş ehtiyat beyinlə gedir): " + ", ".join(closed)] if closed else [])
    out.append(_row("Beyinlərin cavabı", "bütün beyin işləri", "warn" if parts else "ok",
                    "; ".join(parts) if parts else "hər beyin işinin son gündə cavabları 80 %-dən çox uğurlu",
                    len(weak) + len(closed)))

    # 14. the Judge checks itself weekly (20 random rules must fail; rules that peek at the future must be caught)
    try:
        can = json.loads(db.get("judge:canary") or "null")
    except ValueError:
        can = None
    if can is None:
        out.append(_row("Hakimin öz yoxlaması (həftəlik)", "Hakimə etibar", "warn", "hələ işləməyib", None))
    else:
        bad = ([f"{can.get('random_passed')}/{can.get('random_n')} təsadüfi qayda keçdi"]
               if (can.get("random_passed") or 0) > 1 else []) + \
              ([f"son dəfə {(now - can['ts']) / 86400:.0f} gün əvvəl işləyib (həftəlik olmalıdır)"]
               if can.get("ts") and now - can["ts"] > 8 * 86400 else []) + \
              (["30 % gələcəyə baxan saxta qayda nəticəyə görə tutulmadı (o, «inanılmaz yaxşı» həddinin altında qalır; "
                "son sınaqda ayrıca qoruyucu var: proqnoz hədəf vaxtından sonra yazılıbsa sayılmır)"]
               if can.get("peek30_caught") is False else []) + \
              (["tam gələcəyə baxan saxta qayda tutulmadı"] if can.get("peek_caught") is False else [])
        out.append(_row("Hakimin öz yoxlaması (həftəlik)", "Hakimə etibar", "warn" if bad else "ok",
                        "; ".join(bad) if bad else "təsadüfi qaydalar keçmədi, gələcəyə baxanlar tutuldu", len(bad)))

    # 15. what waits for the owner's own step (code ready, a key or a phone needed): shown as such, never as «works»
    for stage, into, st, msg in _owner_steps(db, now):
        out.append(_row(stage, into, st, msg))

    # 16. the daily and hourly sheets the reports are built from: a sheet that stopped being rebuilt shows an old
    # picture as if it were today's (27.11: the block audit called the news block «broken» 17 hours after its fix)
    old = []
    for key, label, limit in FRESH_SHEETS:
        try:
            ts = (json.loads(db.get(key) or "null") or {}).get("computed")
        except (ValueError, AttributeError):
            ts = None
        if ts is None or now - ts > limit:
            old.append(f"{label} ({'heç hesablanmayıb' if ts is None else f'{(now - ts) / 3600:.0f} saat əvvəl'})")
    out.append(_row("Hesabat cədvəlləri (təzəlik)", "Bloklar, Nəticələr, diaqnostika", "warn" if old else "ok",
                    "köhnə: " + "; ".join(old) if old else "hamısı vaxtında yenilənir", len(old)))
    return out


def _owner_steps(db: DB, now: float) -> list[tuple[str, str, str, str]]:
    """Parts whose code is ready but which need the owner (a key, his phone): «owner» while waiting, «ok» only when
    the server's own record shows it working, «bad» when it is set up but failing (a backup error is never green)."""
    out = []
    try:
        from . import heartbeat
        hv = heartbeat.HEART.view() if heartbeat.HEART else {}
    except Exception:
        hv = {}
    setup = hv.get("setup") or {}
    if not hv.get("key"):
        out.append(("Kənar nəzarətçi (Healthchecks.io)", "sahibə dəqiqələr içində xəbər", "owner",
                    "kod hazırdır, sahibin açarını gözləyir; əvəzi: 3 saatlıq növbətçi yoxlama (telefona xəbər)"))
    elif setup.get("ok") is False:
        out.append(("Kənar nəzarətçi (Healthchecks.io)", "sahibə dəqiqələr içində xəbər", "bad",
                    f"açar var, amma qurulmadı: {str(setup.get('note') or '')[:80]}"))
    else:
        out.append(("Kənar nəzarətçi (Healthchecks.io)", "sahibə dəqiqələr içində xəbər", "ok", "işləyir"))
    try:
        b = json.loads(db.get("backup:last") or "null") or {}
    except ValueError:
        b = {}
    msg = str(b.get("msg") or "")
    if b.get("ok") and now - float(b.get("ts") or 0) < 2 * 86400:
        st, text = "ok", "son nüsxə alındı"
    elif not b.get("ok") and "açar" in msg:
        st, text = "owner", "kod hazırdır, sahibin açarını gözləyir; əvəzi: DigitalOcean-ın gündəlik nüsxəsi (7 gün)"
    elif not b:
        st, text = "warn", "hələ heç bir cəhd olmayıb"
    else:
        st, text = "bad", ("son nüsxə 2 gündən köhnədir" if b.get("ok") else f"son cəhd alınmadı: {msg[:80]}")
    out.append(("İkinci ehtiyat nüsxə (Cloudflare R2)", "serverdən kənarda nüsxə", st, text))
    # the two paid feeds the owner chose on 27.11 (plan step 11.1): waiting for the plan and the key, then connected
    fj_saved = bool(db.get("key:financialjuice"))          # sealed value, only whether it exists matters here
    out.append(("FinancialJuice (sürətli başlıqlar)", "Xəbər bloku, həyəcan", "owner",
                "açar Admin-də var — qoşulma növbəti addımdır (Claude)" if fj_saved else
                "sahib almağa qərar verib; açarı Admin → Mənbələr və açarlar bölməsinə yazılandan sonra qoşulur"))
    out.append(("Databento canlı axını (böyük oyunçular, həqiqi həcm)", "Bazar axını bloku, həyəcan", "owner",
                "Standard plan alınandan sonra canlı axın qoşulur (indiki açar yalnız tarixi məlumat üçündür)"))
    try:
        from . import diag, totp
        tf = totp.enabled(db, diag._SEALER[0]) if diag._SEALER else None
    except Exception:
        tf = None
    if tf is not None:
        out.append(("İkiqat yoxlama (2FA)", "girişin qorunması", "ok" if tf else "owner",
                    "açıqdır" if tf else "kod hazırdır, sahibin telefonunu gözləyir; indi: parol + giriş qoruyucusu"))
    return out


def summary(rows: list[dict]) -> dict:
    return {"ok": sum(r["status"] == "ok" for r in rows), "warn": [r["stage"] for r in rows if r["status"] == "warn"],
            "bad": [r["stage"] for r in rows if r["status"] == "bad"]}


def as_json(rows) -> str:
    return json.dumps(rows, ensure_ascii=False)
