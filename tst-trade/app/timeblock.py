"""Vaxt və təqvim bloku (owner 2026-11-25: «why are the cross-market and time blocks not expanded?»).

The calendar effects studied for gold and silver, each as a rule of the Bilik kitabı that our code detects at every
candle close for the NEXT candle and the Judge measures on its own, after costs, like the technical rules. Fixed in
advance from the literature, never tuned on our data:

  session   TM-SES-1 the next hour is in Asian hours (22:00-07:00 UTC): up  (Blose, Gondhalekar & Kort 2018;
                     WGC 2024 session attribution — the old «Seans» method, now a measured rule)
            TM-SES-2 the next hour is in US hours (14:00-20:00 UTC): down
  fixing    TM-FIX-1 the next hour is the London PM fix (15:00 London time): down (Caminschi & Heaney 2014;
                     Abrantes-Metz & Metz 2014; the LBMA auction since 2015 may have removed it: the Judge decides)
  day       TM-DOW-1 the next day is a Monday: down (Lucey & Tully 2006, the Monday effect in gold and silver)
            TM-TOM-1 the next day is in the turn of the month (last trading day, first three): up
                     (Lakonishok & Smidt 1988; the month-end flows)
            TM-HOL-1 the next day is the last trading day before a US market holiday: up (Ariel 1990)
  data hour TM-DATA-1 a big candle in a US data hour (08:30, 10:00 or 14:00 New York): the next hour continues
                     its direction (our own futures study H13: 63.5 % in 104 cases, two years, after costs)

Monthly seasonality («Mövsümilik») and the festival season («Zərgərlik təqvimi») stay as the block's slow methods
for week-to-month horizons (one idea, one place). The block reaches the hour-to-day forecasts as one voice, «vaxt»."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import DB

TM_VER = "2026-11-25.2"     # .2: after Friday comes Monday (the Monday rule never fired)
TFS = ("1h", "1d")                # the calendar rules speak about the next hour or the next day
NY = ZoneInfo("America/New_York")
LON = ZoneInfo("Europe/London")
FAMILY = {"TM-SES-1": "seans", "TM-SES-2": "seans", "TM-FIX-1": "fiksinq", "TM-DOW-1": "gün", "TM-TOM-1": "ay dönüşü",
          "TM-HOL-1": "bayram", "TM-DATA-1": "rəqəm saatı"}
ASIA_HOURS = set(range(22, 24)) | set(range(0, 7))     # UTC
US_HOURS = set(range(14, 20))
DATA_HOURS = {(8, 30), (10, 0), (14, 0)}               # New York


# ---------- US market holidays (NYSE rules) ----------
def _easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    return date(y, month, (h + l_ - 7 * m + 114) % 31 + 1)


def _nth(y: int, m: int, wd: int, n: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last(y: int, m: int, wd: int) -> date:
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() - wd) % 7)


def _observed(d: date) -> date:
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


def us_holidays(y: int) -> set[date]:
    """NYSE full-day holidays of a year."""
    out = {_observed(date(y, 1, 1)), _nth(y, 1, 0, 3), _nth(y, 2, 0, 3), _easter(y) - timedelta(days=2),
           _last(y, 5, 0), _observed(date(y, 7, 4)), _nth(y, 9, 0, 1), _nth(y, 11, 3, 4), _observed(date(y, 12, 25))}
    if y >= 2022:
        out.add(_observed(date(y, 6, 19)))
    return {d for d in out if d.year == y}


def _trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in us_holidays(d.year)


def _day_of(t: float) -> date:
    """The day a daily candle belongs to: our daily candle starts at 22:00 UTC the evening before."""
    return datetime.fromtimestamp(t + 7200, timezone.utc).date()


def detect(tf: str, cs: list[dict], i: int, body_med: float | None = None) -> list[tuple[str, int, str]]:
    """The calendar rules for the candle after candle i (decided at candle i's close)."""
    out = []
    step = {"1h": 3600, "4h": 14400, "1d": 86400}[tf]
    nxt = cs[i]["t"] + step                     # when the next candle starts
    if tf == "1h":
        h = datetime.fromtimestamp(nxt, timezone.utc).hour
        if h in ASIA_HOURS:
            out.append(("TM-SES-1", 1, f"növbəti saat ({h:02d}:00 UTC) Asiya saatlarıdır"))
        elif h in US_HOURS:
            out.append(("TM-SES-2", -1, f"növbəti saat ({h:02d}:00 UTC) ABŞ saatlarıdır"))
        lon = datetime.fromtimestamp(nxt, LON)
        if lon.hour == 15 and lon.weekday() < 5:
            out.append(("TM-FIX-1", -1, "növbəti saat Londonun günorta fiksinqidir (15:00 London)"))
        ny0 = datetime.fromtimestamp(cs[i]["t"], NY)
        ny1 = datetime.fromtimestamp(cs[i]["t"] + step, NY)
        hit = [hm for hm in DATA_HOURS if ny0.weekday() < 5 and
               ny0 <= ny0.replace(hour=hm[0], minute=hm[1]) < ny1]
        body = cs[i]["c"] - cs[i]["o"]
        if hit and body_med and abs(body) >= 2 * body_med:
            hm = hit[0]
            out.append(("TM-DATA-1", 1 if body > 0 else -1, f"ABŞ rəqəmi saatı ({hm[0]:02d}:{hm[1]:02d} NY) böyük şam: "
                                                             f"{'yuxarı' if body > 0 else 'aşağı'}, davamı gözlənilir"))
    if tf == "1d":
        d = _day_of(nxt)
        while d.weekday() >= 5:            # no daily candle on Saturday or Sunday: after Friday comes Monday
            d += timedelta(days=1)
        if d.weekday() == 0:
            out.append(("TM-DOW-1", -1, "sabah bazar ertəsidir"))
        if _trading_day(d):
            nd = d + timedelta(days=1)
            while not _trading_day(nd):
                nd += timedelta(days=1)
            if nd.month != d.month:
                out.append(("TM-TOM-1", 1, "sabah ayın son ticarət günüdür"))
            else:
                k, x = 0, d.replace(day=1)
                while x <= d:
                    k += _trading_day(x)
                    x += timedelta(days=1)
                if k <= 3:
                    out.append(("TM-TOM-1", 1, f"sabah ayın {k}-ci ticarət günüdür"))
            if (nd - d).days > 1 and any(x in us_holidays(x.year) for x in
                                         (d + timedelta(days=j) for j in range(1, (nd - d).days))):
                out.append(("TM-HOL-1", 1, "sabah ABŞ bayramından əvvəlki son ticarət günüdür"))
    return out


def _body_med(cs: list[dict], i: int) -> float | None:
    w = sorted(abs(c["c"] - c["o"]) for c in cs[max(0, i - 100):i])
    return w[len(w) // 2] if len(w) >= 50 else None


def run(db: DB, now: float | None = None) -> int:
    """Each metal and timeframe: the history once (per TM_VER), then the newest candles; the outcome is the next
    candle (and stop + target), exactly as for the technical rules."""
    from . import rules
    from .candles import METALS
    rules.ensure(db)
    now = time.time() if now is None else now
    added = 0
    for sym in METALS:
        for tf in TFS:
            cs = rules._load(db, sym, tf, now)
            if len(cs) < 120:
                continue
            mark = f"tm:ver:{TM_VER}:{sym}:{tf}"
            done = int(db.get(mark) or 0)
            ind = rules.Ind(cs)
            rows = []
            for i in range(110, len(cs)):
                t = cs[i]["t"]
                if t <= done:
                    continue
                p1 = cs[i + 1]["c"] if i + 1 < len(cs) else None
                for rule, d, note in detect(tf, cs, i, _body_med(cs, i) if tf == "1h" else None):
                    rows.append((sym, tf, t, rule, d, cs[i]["c"], p1, "history" if not done else "live", note[:120],
                                 ind.atr[i], ind.adx[i]))
            db.executemany("INSERT OR IGNORE INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note, atr, "
                           "adx) VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
            added += len(rows)
            idx = {x["t"]: k for k, x in enumerate(cs)}
            upd = []
            for r in db.execute("SELECT t, rule, dir, price1 FROM rule_signals WHERE metal=? AND tf=? AND rule LIKE 'TM-%' "
                                "AND (price1 IS NULL OR rr IS NULL)", (sym, tf)).fetchall():
                k = idx.get(r["t"])
                if k is None:
                    continue
                p1 = cs[k + 1]["c"] if k + 1 < len(cs) else None
                res = rules.stop_target(cs, k, r["dir"], ind.atr[k]) if ind.atr[k] else None
                if p1 is not None or res:
                    upd.append((p1 if r["price1"] is None else r["price1"], res[0] if res else None,
                                res[1] if res else None, ind.atr[k], sym, tf, r["t"], r["rule"]))
            if upd:
                db.executemany("UPDATE rule_signals SET price1=?, rr=?, held=?, atr=? WHERE metal=? AND tf=? AND t=? "
                               "AND rule=?", upd)
            db.put(mark, str(cs[-2]["t"]))
    return added


def lookup(db: DB):
    """The block's voice. The calendar is known in advance, so its rules are computed for the very candle being
    forecast (no 30-minute lag as for chart rules); the data-hour rule depends on a candle, so it is read from the
    stored firings with the usual lag. Each rule's weight is its own walk-forward record, as for every block."""
    from .rules import LAG, RULE_TFS, TF_SEC, Lookup

    class Voice(Lookup):
        def views(self, metal: str, t: float, horizon: str) -> dict:
            tfs = [x for x in (self.tfs or RULE_TFS.get(horizon, ("4h", "1d"))) if x in TFS] or ["1d"]
            fam: dict[str, list[float]] = {}
            used = []
            for tf in tfs:
                step = TF_SEC[tf]
                fired = [(r, d) for r, d, _ in detect(tf, [{"t": t - step, "o": 0.0, "c": 0.0}], 0, None)]
                if tf == "1h":           # the data-hour rule: the newest closed candle's firing, with the usual lag
                    now_t = t - LAG
                    fired += [(r, d) for known, tf_, r, d, _ in self.fire.get(metal, [])
                              if r == "TM-DATA-1" and tf_ == tf and now_t - step < known <= now_t]
                for r, d in fired:
                    w, n, hr = self.weight(r, tf, t - LAG)
                    if w <= 0:
                        continue
                    fam.setdefault(FAMILY.get(r, r), []).append(d * w)
                    used.append((w, f"{r} {tf} {'↑' if d > 0 else '↓'} ({round(hr * 100)} %/{n})"))
            if not used:
                return {self.name: (0.5, "indi keçmişi müsbət olan təqvim qaydası yoxdur")}
            vote = sum(sum(v) / len(v) for v in fam.values())
            p = round(0.5 + max(-0.15, min(0.15, 0.5 * vote)), 4)
            used.sort(reverse=True)
            return {self.name: (p, f"{len(used)} qayda, {len(fam)} fikir: " + ", ".join(x for _, x in used[:4]))}

    return Voice(db, prefixes=("TM-",), name="vaxt", families=FAMILY)


# ---------- the block's page (/vaxt) ----------
def page(db: DB, sym: str, tf: str = "1h", now: float | None = None) -> dict:
    """The metal's chart with the rules' firings; the average move by New York hour and by weekday (our own candles,
    last two years: a description, not a forecast); what is ahead on the calendar; the slow methods (season,
    festivals); the vote; the book with the Judge's record."""
    import json as _json
    from . import candles, judge, playbook, rules, slowviews
    rules.ensure(db)
    now = time.time() if now is None else now
    tf = tf if tf in TFS else "1h"
    cs = [dict(r) for r in candles.closed(db, sym, tf, now, limit=600)]
    out: dict = {"symbol": sym, "tf": tf, "ts": now, "candles": cs}
    if not cs:
        return out
    idx = {c["t"]: i for i, c in enumerate(cs)}
    out["fired"] = [{"i": idx[r["t"]], "t": r["t"], "rule": r["rule"], "dir": r["dir"], "note": r["note"]}
                    for r in db.execute("SELECT t, rule, dir, note FROM rule_signals WHERE metal=? AND tf=? AND "
                                        "rule LIKE 'TM-%' AND t>=? ORDER BY t", (sym, tf, cs[0]["t"])).fetchall()
                    if r["t"] in idx]
    hours = {h: [0, 0, 0.0] for h in range(24)}
    for c in candles.closed(db, sym, "1h", now, limit=12000):
        if c["o"]:
            h = datetime.fromtimestamp(c["t"], NY).hour
            r = c["c"] / c["o"] - 1
            hours[h][0] += 1
            hours[h][1] += int(r > 0)
            hours[h][2] += r
    out["by_hour"] = [{"h": h, "n": v[0], "up": round(v[1] / v[0], 4) if v[0] else None,
                       "avg": round(v[2] / v[0] * 100, 4) if v[0] else None} for h, v in hours.items()]
    days = {d: [0, 0, 0.0] for d in range(5)}
    daily = candles.closed(db, sym, "1d", now, limit=700)
    for a, b in zip(daily, daily[1:]):
        d = _day_of(b["t"]).weekday()
        if d < 5 and a["c"]:
            r = b["c"] / a["c"] - 1
            days[d][0] += 1
            days[d][1] += int(r > 0)
            days[d][2] += r
    out["by_day"] = [{"d": d, "n": v[0], "up": round(v[1] / v[0], 4) if v[0] else None,
                      "avg": round(v[2] / v[0] * 100, 4) if v[0] else None} for d, v in days.items()]
    today = datetime.fromtimestamp(now, NY).date()
    ahead = []
    for y in (today.year, today.year + 1):
        for d in sorted(us_holidays(y)):
            if today <= d <= today + timedelta(days=60):
                ahead.append({"date": d.isoformat(), "what": "ABŞ bazarı bağlıdır (bayram)"})
    for name, lst in (("Divali (Hindistan zərgərlik mövsümü)", slowviews.DIWALI), ("Çin Yeni ili", slowviews.LUNAR_NY)):
        for s in lst:
            d = date.fromisoformat(s)
            if today <= d <= today + timedelta(days=120):
                ahead.append({"date": s, "what": name})
    out["ahead"] = sorted(ahead, key=lambda x: x["date"])
    sv = slowviews.Lookup(db).views(sym, now, "1w")
    out["slow"] = {k: {"p": v[0], "basis": v[1]} for k, v in sv.items()}
    try:
        rec = _json.loads(db.get("ta:records") or "null")
    except ValueError:
        rec = None
    if not rec or now - rec.get("ts", 0) > 900:
        rec = {"ts": now, "r": rules.records(db).get("rules", {})}
        db.put("ta:records", _json.dumps(rec, ensure_ascii=False))
    out["book"] = [{"id": r["id"], "name": r["name"], "family": FAMILY.get(r["id"]), "how": r["how"],
                    "signal": r["signal"], "void": r["void"], "source": r["source"],
                    "record": (rec["r"].get(r["id"]) or {}).get(tf)}
                   for r in playbook.RULES if r["area"] == "Vaxt"]
    horizon = {"1h": "1h", "4h": "4h", "1d": "1d"}[tf]
    p, basis = rules.live_lookup(db, "tm").views(sym, now, horizon)["vaxt"]
    st = {r["method"]: r for r in judge.stats(db, sym, horizon, "live", ttl=600)}
    hist = {r["method"]: r for r in judge.stats(db, sym, horizon, "history", ttl=600)}
    pick = lambda m_: (st.get(m_) if (st.get(m_) or {}).get("nh") else hist.get(m_)) or {}
    out["now"] = {"t": cs[-1]["t"], "vote": {"p": p, "basis": basis},
                  "rules": [f for f in out["fired"] if f["t"] == cs[-1]["t"]],
                  "judge": {"vaxt": {k: pick("vaxt").get(k) for k in ("nh", "hit_rate", "bar", "status")}}}
    return out
