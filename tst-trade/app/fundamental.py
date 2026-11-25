"""Fundamental blok (owner 2026-11-25: «every block as complete as the technical one»).

The drivers professionals use for gold (World Gold Council GRAM: opportunity cost, risk, economic expansion, central-bank
demand; dollar; Fed path; positioning; data surprises), each as a rule of the Bilik kitabı that our code detects on
every trading day and the Judge measures on its own (next daily candle and stop + target, like the technical rules).

Timing: a daily candle labelled D is decided at its close; only values PUBLISHED by then are used (FRED daily series
come out the next afternoon: lag 2 days; the broad dollar index weekly: lag 10 days; COT on Friday for the Tuesday).
Stored in rule_signals (tf «1d», ids FA-*), so the records, the stop + target test and the walk-forward weights are
the same machinery as the technical block. The block reaches the forecasts as one voice, «fundamental»."""
from __future__ import annotations

import bisect
import time
from datetime import datetime, timezone

from .db import DB

LAG_DAYS = {"DFII10": 2, "DGS2": 2, "T10YIE": 2, "DTWEXBGS": 10, "DEXCHUS": 2}
GROW_PUBLIC_DAYS = 60     # CFNAI for a month (dated its first day) comes out about three to four weeks after it ends
OZ_G = 31.1035
COT_PUBLIC = 3 * 86400 + 20 * 3600 + 1800        # Tuesday 00:00 UTC -> Friday 20:30 UTC
FA_VER = "2026-11-25.5"
FAMILY = {"FA-RY-1": "faiz", "FA-RY-2": "faiz", "FA-FED-1": "faiz", "FA-BE-1": "faiz", "FA-USD-1": "dollar",
          "FA-COT-1": "mövqe", "FA-COT-2": "mövqe", "FA-SURP-1": "sürpriz", "FA-CB-1": "mərkəzi bank",
          "FA-FED-2": "faiz", "FA-SGE-1": "fiziki tələb", "FA-GROW-1": "böyümə",
          "FA-ETF-1": "ETF axını", "FA-ETF-2": "ETF axını", "FA-IND-1": "fiziki tələb", "FA-IND-2": "fiziki tələb"}
FED_BPS = {"H26": 50, "H25": 25, "H0": 0, "C25": -25, "C26": -50}
OZ_PER_TONNE = 32150.7466
CB_PUBLIC_DAYS = 45      # a month's IMF figure is public about six weeks after the month ends (counted cautiously)


class Data:
    """Every input as it was known at a moment (no revisions from the future: ALFRED first values where kept)."""

    def __init__(self, db: DB):
        self.series: dict[str, tuple[list[str], list[float]]] = {}
        for sid in LAG_DAYS:
            try:
                rows = db.execute("SELECT d, v FROM macro WHERE series=? ORDER BY d", (sid,)).fetchall()
                first = {r["d"]: r["v"] for r in db.execute("SELECT d, v FROM macro_first WHERE series=?",
                                                            (sid,)).fetchall()}
            except Exception:
                rows, first = [], {}
            self.series[sid] = ([r["d"] for r in rows], [first.get(r["d"], r["v"]) for r in rows])
        self.cot: dict[str, tuple[list[float], list[float]]] = {}
        try:
            for r in db.execute("SELECT symbol, d, mm_long, mm_short FROM cot ORDER BY d").fetchall():
                t = datetime.fromisoformat(r["d"]).replace(tzinfo=timezone.utc).timestamp() + COT_PUBLIC
                ts, nets = self.cot.setdefault(r["symbol"], ([], []))
                ts.append(t)
                nets.append((r["mm_long"] or 0) - (r["mm_short"] or 0))
        except Exception:
            pass
        from . import surprise
        self.sur = surprise.Lookup(db)
        # Fed path from the prediction market (Kalshi): the expected change at the next meeting, in basis points
        self.fed_t: list[float] = []
        self.fed_bps: list[float] = []
        try:
            snap: dict[float, dict] = {}
            for r in db.execute("SELECT ts, ticker, prob, close_ts FROM fed_odds WHERE ticker LIKE 'KXFEDDECISION-%' "
                                "ORDER BY ts").fetchall():
                code = r["ticker"].rsplit("-", 1)[-1]
                if code in FED_BPS and r["close_ts"] and r["close_ts"] > r["ts"] and r["prob"] is not None:
                    by = snap.setdefault(round(r["ts"]), {})
                    by.setdefault(r["close_ts"], {})[code] = r["prob"]
            for ts in sorted(snap):
                meet = min(snap[ts])                     # the next meeting
                probs = snap[ts][meet]
                tot = sum(probs.values())
                if len(probs) >= 3 and tot > 0.5:
                    self.fed_t.append(ts)
                    self.fed_bps.append(sum(FED_BPS[c] * p for c, p in probs.items()) / tot)
        except Exception:
            pass
        # Shanghai premium: SGE Au99.99 (yuan/g) in dollars per ounce against our gold close the same day
        self.sge_t: list[float] = []
        self.sge_prem: list[float] = []
        try:
            xau = {datetime.fromtimestamp(r["t"], timezone.utc).strftime("%Y-%m-%d"): r["c"] for r in db.execute(
                "SELECT t, c FROM candles WHERE symbol='XAU' AND tf='1d'").fetchall()}
            cny_d, cny_v = self.series.get("DEXCHUS", ([], []))
            for r in db.execute("SELECT d, close FROM sge_gold ORDER BY d").fetchall():
                j = bisect.bisect_right(cny_d, r["d"]) - 1
                if j < 0 or r["d"] not in xau or not cny_v[j]:
                    continue
                usd_oz = r["close"] * OZ_G / cny_v[j]
                self.sge_t.append(datetime.fromisoformat(r["d"]).replace(tzinfo=timezone.utc).timestamp() + 86400)
                self.sge_prem.append(usd_oz / xau[r["d"]] - 1)
        except Exception:
            pass
        # ETF flow: GLD's tonnes per day (the issuer publishes by 16:45 New York; counted known the next day)
        try:
            etf = db.execute("SELECT d, tonnes FROM etf_gold WHERE fund='GLD' ORDER BY d").fetchall()
        except Exception:
            etf = []
        self.etf_t = [datetime.fromisoformat(r["d"]).replace(tzinfo=timezone.utc).timestamp() + 86400 for r in etf]
        self.etf_v = [r["tonnes"] for r in etf]
        from . import reporter                  # India, from news reports confirmed by two brains (Bazar müxbiri)
        try:
            self.ind_prem = reporter.accepted(db, "india_premium")
            self.ind_etf = reporter.accepted(db, "india_etf")
        except Exception:
            self.ind_prem, self.ind_etf = [], []
        try:
            rows = db.execute("SELECT d, v FROM macro WHERE series='CFNAIMA3' ORDER BY d").fetchall()
        except Exception:
            rows = []
        self.grow_t = [datetime.fromisoformat(r["d"]).replace(tzinfo=timezone.utc).timestamp() + GROW_PUBLIC_DAYS * 86400
                       for r in rows]
        self.grow_v = [r["v"] for r in rows]
        # central banks' net purchases per month (tonnes), with the moment each month became public
        self.cb_t: list[float] = []
        self.cb_net: list[float] = []
        try:
            by: dict[str, dict[str, float]] = {}
            for r in db.execute("SELECT country, period, oz FROM cb_gold").fetchall():
                by.setdefault(r["period"], {})[r["country"]] = r["oz"]
            months = sorted(by)
            for a, b in zip(months, months[1:]):
                both = set(by[a]) & set(by[b])           # only countries reported in both months
                if len(both) < 5:
                    continue
                net = sum(by[b][c] - by[a][c] for c in both) / OZ_PER_TONNE
                y, m = int(b[:4]), int(b[5:7])
                end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc).timestamp()
                self.cb_t.append(end + CB_PUBLIC_DAYS * 86400)
                self.cb_net.append(net)
        except Exception:
            pass

    def change(self, sid: str, t: float, days: int, pct: bool = False) -> float | None:
        """The change over `days` observations of the last value published before t."""
        ds, vs = self.series.get(sid, ([], []))
        day = datetime.fromtimestamp(t - (LAG_DAYS[sid] - 1) * 86400, timezone.utc).strftime("%Y-%m-%d")
        i = bisect.bisect_left(ds, day) - 1
        if i < days:
            return None
        a, b = vs[i - days], vs[i]
        return (b / a - 1) * 100 if pct else b - a

    def cot_at(self, metal: str, t: float) -> list[float]:
        ts, nets = self.cot.get(metal, ([], []))
        i = bisect.bisect_right(ts, t)
        return nets[max(0, i - 156):i]

    def surprise_sum(self, t: float, days: int = 14) -> tuple[float, int]:
        lo = bisect.bisect_left(self.sur.ts, t - days * 86400)
        hi = bisect.bisect_right(self.sur.ts, t)
        items = self.sur.items[lo:hi]
        return sum(s["gold"] * s["weight"] for s in items), len(items)


def detect(data: Data, metal: str, t: float) -> list[tuple[str, int, str]]:
    """The fundamental rules at moment t (what was published by then)."""
    out = []
    r5 = data.change("DFII10", t, 5)
    if r5 is not None and abs(r5) >= 0.10:
        out.append(("FA-RY-1", 1 if r5 < 0 else -1, f"real faiz 5 günə {r5:+.2f} pp"))
    r20 = data.change("DFII10", t, 20)
    if r20 is not None and abs(r20) >= 0.25:
        out.append(("FA-RY-2", 1 if r20 < 0 else -1, f"real faiz 20 günə {r20:+.2f} pp (trend)"))
    y2 = data.change("DGS2", t, 5)
    if y2 is not None and abs(y2) >= 0.15:
        out.append(("FA-FED-1", 1 if y2 < 0 else -1, f"2 illik faiz 5 günə {y2:+.2f} pp: bazar Fed-dən "
                                                      f"{'daha çox endirim' if y2 < 0 else 'daha az endirim'} gözləyir"))
    be = data.change("T10YIE", t, 5)
    if be is not None and abs(be) >= 0.08:
        out.append(("FA-BE-1", 1 if be > 0 else -1, f"inflyasiya gözləntisi 5 günə {be:+.2f} pp"))
    usd = data.change("DTWEXBGS", t, 5, pct=True)
    if usd is not None and abs(usd) >= 1.0:
        out.append(("FA-USD-1", 1 if usd < 0 else -1, f"geniş dollar indeksi 5 günə {usd:+.2f} %"))
    past = data.cot_at(metal, t)
    if len(past) >= 104:
        now = past[-1]
        pct = sum(x < now for x in past) / len(past) * 100
        if pct >= 80:
            out.append(("FA-COT-1", -1, f"fondlar çox alıb (3 ilin {pct:.0f}-ci faizi)"))
        elif pct <= 20:
            out.append(("FA-COT-1", 1, f"fondlar çox satıb (3 ilin {pct:.0f}-ci faizi)"))
        d = [b - a for a, b in zip(past[-4:], past[-3:])]
        moves = sorted(abs(b - a) for a, b in zip(past, past[1:]))
        big = moves[int(len(moves) * 0.6)] if moves else 0
        if len(d) == 3 and (all(x > 0 for x in d) or all(x < 0 for x in d)) and abs(sum(d)) >= 3 * big:
            out.append(("FA-COT-2", 1 if d[0] > 0 else -1, "fondlar 3 həftədir ardıcıl " +
                        ("alır" if d[0] > 0 else "satır")))
    i = bisect.bisect_right(data.cb_t, t)
    nets = data.cb_net[:i]
    if len(nets) >= 27:
        sums = [sum(nets[k - 3:k]) for k in range(3, len(nets) + 1)][-36:]
        now3 = sums[-1]
        pct = sum(x < now3 for x in sums) / len(sums) * 100
        if pct >= 80:
            out.append(("FA-CB-1", 1, f"mərkəzi banklar son 3 ayda {now3:+.0f} ton aldı: 3 ilin ən güclü alışları "
                                      f"({pct:.0f}-ci faiz)"))
        elif pct <= 20:
            out.append(("FA-CB-1", -1, f"mərkəzi banklar son 3 ayda {now3:+.0f} ton: 3 ilin ən zəif alışları "
                                       f"({pct:.0f}-ci faiz)"))
    k = bisect.bisect_right(data.fed_t, t)
    if k:
        now_b = data.fed_bps[k - 1]
        j = bisect.bisect_right(data.fed_t, t - 3 * 86400)
        if j and data.fed_t[k - 1] - data.fed_t[j - 1] >= 2 * 86400:
            ch = now_b - data.fed_bps[j - 1]
            if abs(ch) >= 5:
                out.append(("FA-FED-2", 1 if ch < 0 else -1, f"Kalshi: növbəti Fed iclasından gözlənilən dəyişmə 3 günə "
                                                             f"{ch:+.0f} bp (indi {now_b:+.0f} bp)"))
    k = bisect.bisect_right(data.sge_t, t)
    prem = data.sge_prem[:k][-250:]
    if len(prem) >= 120:
        cur = sum(prem[-5:]) / 5
        pct = sum(x < cur for x in prem) / len(prem) * 100
        if pct >= 80:
            out.append(("FA-SGE-1", 1, f"Şanxay premiumu {cur * 100:+.2f} %: ilin ən yüksək {100 - pct:.0f} %-i (Çin "
                                       f"tələbi güclü)"))
        elif pct <= 20:
            out.append(("FA-SGE-1", -1, f"Şanxay premiumu {cur * 100:+.2f} %: ilin ən aşağı {pct:.0f} %-i (Çin tələbi zəif)"))
    k = bisect.bisect_right(data.etf_t, t)
    tn = data.etf_v[max(0, k - 300):k]
    for rule, w, label in (("FA-ETF-1", 5, "5 gündə"), ("FA-ETF-2", 20, "20 gündə")):
        if len(tn) > 250 + w:
            flows = [tn[j] - tn[j - w] for j in range(w, len(tn))][-250:]
            cur = flows[-1]
            pct = sum(x < cur for x in flows) / len(flows) * 100
            if pct >= 80 and cur > 0:
                out.append((rule, 1, f"GLD {label} {cur:+.1f} ton aldı: ilin ən güclü girişlərindən ({pct:.0f}-ci faiz)"))
            elif pct <= 20 and cur < 0:
                out.append((rule, -1, f"GLD {label} {cur:+.1f} ton itirdi: ilin ən güclü çıxışlarından ({pct:.0f}-ci faiz)"))
    known = [x for x in data.ind_prem if x[0] <= t]
    if len(known) >= 2 and t - known[-1][0] <= 14 * 86400:
        ch = known[-1][2] - known[-2][2]
        if abs(ch) >= 5:
            out.append(("FA-IND-1", 1 if ch > 0 else -1, f"Hindistan premiumu {known[-2][2]:+.0f} → {known[-1][2]:+.0f} $/unsiya "
                                                         f"({'tələb güclənir' if ch > 0 else 'tələb zəifləyir'})"))
    etf = [x for x in data.ind_etf if x[0] <= t]
    if etf and t - etf[-1][0] <= 45 * 86400 and abs(etf[-1][2]) >= 500:
        v = etf[-1][2]
        out.append(("FA-IND-2", 1 if v > 0 else -1, f"Hindistanın qızıl ETF-lərinə {etf[-1][1]} ayında xalis "
                                                    f"{'giriş' if v > 0 else 'çıxış'} {v:+,.0f} krore rupi"))
    k = bisect.bisect_right(data.grow_t, t)
    if k:
        g = data.grow_v[k - 1]
        if g >= 0.2:
            out.append(("FA-GROW-1", 1, f"ABŞ iqtisadi fəallığı yüksəlir (CFNAI-MA3 {g:+.2f})"))
        elif g <= -0.7:
            out.append(("FA-GROW-1", -1, f"ABŞ iqtisadi fəallığı tənəzzül həddində (CFNAI-MA3 {g:+.2f})"))
    s, n = data.surprise_sum(t)
    if n >= 3 and abs(s) >= 2:
        out.append(("FA-SURP-1", 1 if s > 0 else -1, f"son 14 gündə {n} ABŞ rəqəmi: sürprizlər qızıl üçün "
                                                     f"{'müsbət' if s > 0 else 'mənfi'} ({s:+.1f})"))
    return out


def run(db: DB, now: float | None = None) -> int:
    """Detect on every daily candle (history once, then the newest); next candle and stop + target as for TA rules."""
    from . import candles, rules
    from .candles import METALS
    rules.ensure(db)
    now = time.time() if now is None else now
    data = Data(db)
    added = 0
    for sym in METALS:
        cs = [dict(r) for r in candles.closed(db, sym, "1d", now, limit=4500)]
        if len(cs) < 30:
            continue
        ind = rules.Ind(cs)
        # replayed again once the central-bank data first arrives (the IMF feed runs once a day)
        have = "".join(x for x, ok in (("c", data.cb_net), ("s", data.sge_prem), ("g", data.grow_v), ("e", data.etf_v),
                                         ("i", data.ind_prem)) if ok)
        mark = f"fa:ver:{FA_VER}:{have}:{sym}"
        done = int(db.get(mark) or 0)
        rows = []
        for i in range(20, len(cs)):
            t = cs[i]["t"]
            if t <= done:
                continue
            known = t + 86400 - 7200            # the candle's close (22:00 UTC): what was published by then
            p1 = cs[i + 1]["c"] if i + 1 < len(cs) else None
            for rule, d, note in detect(data, sym, known):
                rows.append((sym, "1d", t, rule, d, cs[i]["c"], p1, "history" if not done else "live", note[:120],
                             ind.atr[i], ind.adx[i]))
        db.executemany("INSERT OR IGNORE INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note, atr, adx) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
        added += len(rows)
        idx = {x["t"]: k for k, x in enumerate(cs)}
        upd = []
        for r in db.execute("SELECT t, rule, dir, price1 FROM rule_signals WHERE metal=? AND tf='1d' AND rule LIKE 'FA-%' "
                            "AND (price1 IS NULL OR rr IS NULL)", (sym,)).fetchall():
            k = idx.get(r["t"])
            if k is None:
                continue
            p1 = cs[k + 1]["c"] if k + 1 < len(cs) else None
            res = rules.stop_target(cs, k, r["dir"], ind.atr[k]) if ind.atr[k] else None
            if p1 is not None or res:
                upd.append((p1 if r["price1"] is None else r["price1"], res[0] if res else None,
                            res[1] if res else None, ind.atr[k], sym, r["t"], r["rule"]))
        if upd:
            db.executemany("UPDATE rule_signals SET price1=?, rr=?, held=?, atr=? WHERE metal=? AND tf='1d' AND t=? "
                           "AND rule=?", upd)
        db.put(mark, str(cs[-2]["t"]))
    return added


# ---------- the block's page (/fundamental) ----------
FACTORS = [  # what each line is, and which way is good for gold
    {"id": "DFII10", "name": "Real faiz (10 il, TIPS), %", "good": -1},
    {"id": "DGS2", "name": "2 illik faiz (Fed gözləntisi), %", "good": -1},
    {"id": "T10YIE", "name": "İnflyasiya gözləntisi (10 il), %", "good": 1},
    {"id": "DTWEXBGS", "name": "Geniş dollar indeksi", "good": -1},
    {"id": "CFNAIMA3", "name": "ABŞ iqtisadi fəallığı (CFNAI-MA3)", "good": 1},
]


def page(db: DB, sym: str, now: float | None = None) -> dict:
    """Everything the fundamental page shows, from the block itself: the gold daily chart with the rules' firings,
    each driver over the last two years, the central banks' monthly buying, COT, the surprise index, the vote and
    the book with the Judge's record."""
    import json as _json
    from . import candles, judge, playbook, rules
    rules.ensure(db)
    now = time.time() if now is None else now
    cs = [dict(r) for r in candles.closed(db, sym, "1d", now, limit=600)]
    out: dict = {"symbol": sym, "ts": now, "candles": cs}
    if not cs:
        return out
    t0 = cs[max(0, len(cs) - 520)]["t"]
    idx = {c["t"]: i for i, c in enumerate(cs)}
    out["fired"] = [{"i": idx[r["t"]], "t": r["t"], "rule": r["rule"], "dir": r["dir"], "note": r["note"]}
                    for r in db.execute("SELECT t, rule, dir, note FROM rule_signals WHERE metal=? AND tf='1d' "
                                        "AND rule LIKE 'FA-%' AND t>=? ORDER BY t", (sym, cs[0]["t"])).fetchall()
                    if r["t"] in idx]
    day0 = datetime.fromtimestamp(t0, timezone.utc).strftime("%Y-%m-%d")
    fac = []
    for f in FACTORS:
        try:
            pts = [[datetime.fromisoformat(r["d"]).replace(tzinfo=timezone.utc).timestamp(), r["v"]]
                   for r in db.execute("SELECT d, v FROM macro WHERE series=? AND d>=? ORDER BY d", (f["id"], day0))]
        except Exception:
            pts = []
        fac.append({**f, "pts": pts})
    data = Data(db)
    ts, nets = data.cot.get(sym, ([], []))
    fac.append({"id": "COT", "name": "Fondların xalis mövqeyi (COT, kontrakt)", "good": 0,
                "pts": [[t, v] for t, v in zip(ts, nets) if t >= t0]})
    fac.append({"id": "SGE", "name": "Şanxay premiumu (Çin tələbi), %", "good": 1,
                "pts": [[t, round(v * 100, 3)] for t, v in zip(data.sge_t, data.sge_prem) if t >= t0]})
    fac.append({"id": "ETF", "name": "GLD ETF-in qızılı, ton (ETF axını)", "good": 1,
                "pts": [[t, v] for t, v in zip(data.etf_t, data.etf_v) if t >= t0]})
    fac.append({"id": "IND", "name": "Hindistan premiumu/endirimi, $/unsiya (xəbərlərdən, Bazar müxbiri)", "good": 1,
                "pts": [[t, v] for t, _, v in data.ind_prem]})
    fac.append({"id": "FED", "name": "Kalshi: növbəti Fed iclasında gözlənilən dəyişmə, bp", "good": -1,
                "pts": [[t, round(v, 1)] for t, v in zip(data.fed_t, data.fed_bps) if t >= t0]})
    out["factors"] = fac
    out["cb"] = [[t, round(v, 1)] for t, v in zip(data.cb_t, data.cb_net) if t >= t0 - 365 * 86400]
    sur = []
    for c in cs:
        if c["t"] >= t0:
            s, n = data.surprise_sum(c["t"] + 86400 - 7200)
            sur.append([c["t"], round(s, 2), n])
    out["surprise"] = sur
    try:
        rec = _json.loads(db.get("ta:records") or "null")
    except ValueError:
        rec = None
    if not rec or now - rec.get("ts", 0) > 900:
        rec = {"ts": now, "r": rules.records(db).get("rules", {})}
        db.put("ta:records", _json.dumps(rec, ensure_ascii=False))
    out["book"] = [{"id": r["id"], "name": r["name"], "family": FAMILY.get(r["id"]), "how": r["how"],
                    "signal": r["signal"], "void": r["void"], "source": r["source"],
                    "record": (rec["r"].get(r["id"]) or {}).get("1d")}
                   for r in playbook.RULES if r["area"] == "Fundamental"]
    last_t = cs[-1]["t"]
    p, basis = rules.live_lookup(db, "fa").views(sym, now, "1d")["fundamental"]
    st = {r["method"]: r for r in judge.stats(db, sym, "1d", "live", ttl=600)}
    hist = {r["method"]: r for r in judge.stats(db, sym, "1d", "history", ttl=600)}
    pick = lambda m: (st.get(m) if (st.get(m) or {}).get("nh") else hist.get(m)) or {}
    out["now"] = {"t": last_t, "vote": {"p": p, "basis": basis},
                  "rules": [f for f in out["fired"] if f["t"] == last_t],
                  "judge": {m: {k: pick(m).get(k) for k in ("nh", "hit_rate", "bar", "status")}
                            for m in ("fundamental", "surprise", "strateq")}}
    from . import cards
    card = next((c for c in cards.recent(db, sym, 60) if c["source"] == "strateq" and c["horizon"] == "1d"), None)
    if card:
        out["now"]["strateq"] = {"p": card["p_cal"] if card["p_cal"] is not None else card["p"], "ts": card["known_ts"],
                                 "scenario": card["scenario"], "counter": card["counter"]}
    return out
