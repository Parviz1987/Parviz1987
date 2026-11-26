"""Xəbər bloku (owner 2026-11-25: «every block as complete as the technical one»).

What professionals use news for, each as a rule of the Bilik kitabı measured by the Judge (next 1-hour candle and
stop + target, like the technical rules):
- sentiment with asymmetry and decay: negative news moves gold more than positive (Smales 2014, 2015) and a headline's
  effect fades over hours (exponential decay, half-life about 2 hours);
- by topic: the Fed, US data (inflation, jobs), geopolitics (the safe-haven channel; Baur-Smales 2020; Apergis et al.
  2021: geopolitical news has the stronger effect), physical supply and demand;
- attention: a burst of headlines far above the usual flow;
- a single major headline (strength 3).
Inputs: the Reader's labels (metal, direction, strength 0-3, topic) on the FIRST headline of each news event (copies of
the same story are not read again), each counted from the moment it was labelled (known time) — never before.
The block's voice «xeber» is computed at any moment from these rules, each weighted by its own record known then."""
from __future__ import annotations

import bisect
import math
import time

from .db import DB

NW_VER = "2026-11-26.2"   # .2: only the burst rule waits for a week of labels; scheduled news fades faster (replay)
TOPIC = {"fed": "fed", "monetary": "fed", "rates": "fed", "inflation": "data", "jobs": "data", "gdp": "data",
         "data": "data", "geopolitics": "geo", "war": "geo", "sanctions": "geo", "supply": "flow", "demand": "flow"}
FAMILY = {"NW-SENT-1": "əhval", "NW-FED-1": "Fed", "NW-DATA-1": "ABŞ rəqəmi", "NW-GEO-1": "geosiyasət",
          "NW-FLOW-1": "tələb-təklif", "NW-SURGE-1": "axın sıçrayışı", "NW-SHOCK-1": "böyük xəbər"}
HALF_LIFE = 2 * 3600
# scheduled US data and Fed news are absorbed by gold within minutes (Smales 2015: ~90 s; Awartani et al. 2024: some
# drift past 5 min) — their weight halves every hour, other news every 2 hours (research 2026-11-26)
HALF_LIFE_TOPIC = {"data": 3600, "fed": 3600}
NEG = 1.5               # a negative headline weighs 1.5 times a positive one (asymmetry)


def topic_of(event: str | None) -> str:
    e = (event or "").lower()
    for k, v in TOPIC.items():
        if k in e:
            return v
    return "other"


class Data:
    """The Reader's labels per metal, in time order of when they became known."""

    def __init__(self, db: DB):
        self.by: dict[str, list[tuple[float, int, int, str]]] = {}     # metal -> [(known_ts, dir, strength, topic)]
        try:
            rows = db.execute("SELECT ts, metals, direction, strength, event FROM news_ai ORDER BY ts").fetchall()
        except Exception:
            rows = []
        for r in rows:
            d = 1 if r["direction"] == "up" else -1 if r["direction"] == "down" else 0
            s = int(r["strength"] or 0)
            for m in (r["metals"] or "").split(","):
                if m:
                    self.by.setdefault(m, []).append((r["ts"], d, s, topic_of(r["event"])))
        self.ts = {m: [x[0] for x in v] for m, v in self.by.items()}

    def window(self, metal: str, t: float, back: float) -> list[tuple[float, int, int, str]]:
        ts = self.ts.get(metal, [])
        lo, hi = bisect.bisect_left(ts, t - back), bisect.bisect_right(ts, t)
        return self.by.get(metal, [])[lo:hi]

    def first(self, metal: str) -> float | None:
        ts = self.ts.get(metal)
        return ts[0] if ts else None


def _score(items, t: float) -> float:
    return sum(d * s * (NEG if d < 0 else 1.0) * math.exp(-(t - k) * math.log(2) / HALF_LIFE_TOPIC.get(top, HALF_LIFE))
               for k, d, s, top in items)


def detect(data: Data, metal: str, t: float) -> list[tuple[str, int, str]]:
    out = []
    first = data.first(metal)
    if first is None:
        return out
    week_known = t - first >= 7 * 86400   # only the burst rule needs a week of labels (its «usual flow»): 2026-11-26
    # the other rules used to wait for it too, so the voice stayed silent for its whole first week
    recent = data.window(metal, t, 6 * 3600)
    sc = _score(recent, t)
    if abs(sc) >= 3:
        out.append(("NW-SENT-1", 1 if sc > 0 else -1, f"son 6 saatın xəbər əhvalı {sc:+.1f} (mənfi xəbər 1,5 qat, "
                                                       f"2 saatda yarıya sönür)"))
    four = data.window(metal, t, 4 * 3600)
    for rule, top, name in (("NW-FED-1", "fed", "Fed"), ("NW-DATA-1", "data", "ABŞ rəqəmləri"),
                            ("NW-GEO-1", "geo", "geosiyasət"), ("NW-FLOW-1", "flow", "tələb-təklif")):
        s = _score([x for x in four if x[3] == top], t)
        if abs(s) >= 2:
            out.append((rule, 1 if s > 0 else -1, f"son 4 saatda «{name}» xəbərləri: {s:+.1f}"))
    burst = [x for x in data.window(metal, t, 2 * 3600) if x[2] > 0]
    week = [x for x in data.window(metal, t - 2 * 3600, 7 * 86400) if x[2] > 0]
    usual = len(week) / (7 * 12)                     # labelled headlines per 2 hours over the last week
    if week_known and len(burst) >= 4 and len(burst) >= 3 * max(usual, 0.5):
        net = sum(d * s for _, d, s, _ in burst)
        if net:
            out.append(("NW-SURGE-1", 1 if net > 0 else -1, f"2 saatda {len(burst)} xəbər (adi {usual:.1f}): axın "
                                                             f"sıçrayışı, əhval {net:+d}"))
    big = [x for x in data.window(metal, t, 3600) if x[2] == 3 and x[1]]
    if big:
        d = big[-1][1]
        out.append(("NW-SHOCK-1", d, f"son saatda böyük xəbər (güc 3): {'yuxarı' if d > 0 else 'aşağı'}"))
    return out


def run(db: DB, now: float | None = None) -> int:
    """Detect on every closed 1-hour candle (history once, then the newest); next candle and stop + target."""
    from . import candles, rules
    from .candles import METALS
    rules.ensure(db)
    now = time.time() if now is None else now
    data = Data(db)
    added = 0
    for sym in METALS:
        if data.first(sym) is None:
            continue
        cs = [dict(r) for r in candles.closed(db, sym, "1h", now, limit=4500)]
        if len(cs) < 30:
            continue
        ind = rules.Ind(cs)
        mark = f"nw:ver:{NW_VER}:{sym}"
        done = int(db.get(mark) or 0)
        if not done:          # a new version: the old replayed history goes (live firings are kept)
            db.execute("DELETE FROM rule_signals WHERE metal=? AND mode='history' AND rule LIKE 'NW-%'", (sym,))
        rows = []
        for i in range(20, len(cs)):
            t = cs[i]["t"]
            if t <= done or t + 3600 < data.first(sym):
                continue
            p1 = cs[i + 1]["c"] if i + 1 < len(cs) else None
            for rule, d, note in detect(data, sym, t + 3600):
                rows.append((sym, "1h", t, rule, d, cs[i]["c"], p1, "history" if not done else "live", note[:120],
                             ind.atr[i], ind.adx[i]))
        db.executemany("INSERT OR IGNORE INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note, atr, adx) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
        added += len(rows)
        idx = {x["t"]: k for k, x in enumerate(cs)}
        upd = []
        for r in db.execute("SELECT t, rule, dir, price1, rr FROM rule_signals WHERE metal=? AND tf='1h' "
                            "AND rule LIKE 'NW-%' AND (price1 IS NULL OR rr IS NULL)", (sym,)).fetchall():
            k = idx.get(r["t"])
            if k is None:
                continue
            p1 = cs[k + 1]["c"] if k + 1 < len(cs) else None
            res = rules.stop_target(cs, k, r["dir"], ind.atr[k]) if ind.atr[k] else None
            if (p1 is not None and r["price1"] is None) or res:
                upd.append((r["price1"] if r["price1"] is not None else p1, res[0] if res else None,
                            res[1] if res else None, ind.atr[k], sym, r["t"], r["rule"]))
        if upd:
            db.executemany("UPDATE rule_signals SET price1=?, rr=?, held=?, atr=? WHERE metal=? AND tf='1h' AND t=? "
                           "AND rule=?", upd)
        db.put(mark, str(cs[-2]["t"]))
    return added


class Voice:
    """«xeber»: the news rules firing NOW (computed at the moment, no lag), each weighted by its record known then
    (the stored hourly firings, walk-forward), one voice per idea."""

    def __init__(self, db: DB):
        from . import rules
        self.data = Data(db)
        self.rec = rules.Lookup(db, prefixes=("NW-",), name="xeber", tfs=("1h",), families=FAMILY)

    def views(self, metal: str, t: float, horizon: str) -> dict:
        if horizon not in ("15m", "30m", "1h", "4h", "1d"):
            return {}
        fires = detect(self.data, metal, t - 60)
        fam: dict[str, list[float]] = {}
        used = []
        for rule, d, note in fires:
            w, n, hr = self.rec.weight(rule, "1h", t)
            if w <= 0:
                continue
            fam.setdefault(FAMILY.get(rule, rule), []).append(d * w)
            used.append((w, f"{rule} {'↑' if d > 0 else '↓'} ({round(hr * 100)} %/{n})"))
        if not used:
            why = "indi keçmişi müsbət olan xəbər qaydası işə düşməyib" if fires else "indi xəbər qaydası işə düşməyib"
            return {"xeber": (0.5, why)}
        vote = sum(sum(v) / len(v) for v in fam.values())
        p = round(0.5 + max(-0.15, min(0.15, 0.5 * vote)), 4)
        used.sort(reverse=True)
        return {"xeber": (p, f"{len(used)} qayda, {len(fam)} fikir: " + ", ".join(x for _, x in used[:4]))}


_LIVE: dict = {}


def live_voice(db: DB) -> Voice:
    hit = _LIVE.get("v")
    if hit is None or time.time() - hit[0] > 300:
        hit = (time.time(), Voice(db))
        _LIVE["v"] = hit
    return hit[1]


TOPIC_NAMES = {"fed": "Fed", "data": "ABŞ rəqəmi", "geo": "geosiyasət", "flow": "tələb-təklif", "other": "digər"}


def page(db: DB, sym: str, now: float | None = None) -> dict:
    """The news page: 1-hour candles with the news rules' firings, the latest labelled headlines, the mood by topic
    over the last 24 hours, the voice now and the book with the Judge's record."""
    import json as _json
    from . import candles, judge, playbook, rules
    rules.ensure(db)
    now = time.time() if now is None else now
    cs = [dict(r) for r in candles.closed(db, sym, "1h", now, limit=400)]
    out: dict = {"symbol": sym, "ts": now, "candles": cs}
    idx = {c["t"]: i for i, c in enumerate(cs)}
    out["fired"] = [{"i": idx[r["t"]], "t": r["t"], "rule": r["rule"], "dir": r["dir"], "note": r["note"]}
                    for r in db.execute("SELECT t, rule, dir, note FROM rule_signals WHERE metal=? AND tf='1h' "
                                        "AND rule LIKE 'NW-%' AND t>=? ORDER BY t", (sym, cs[0]["t"] if cs else now))
                    if r["t"] in idx]
    try:
        heads = db.execute(
            "SELECT a.ts, a.event, a.direction, a.strength, n.title, n.source FROM news_ai a LEFT JOIN news n ON n.uid=a.uid "
            "WHERE (',' || a.metals || ',') LIKE ? AND a.ts > ? ORDER BY a.ts DESC LIMIT 40",
            (f"%,{sym},%", now - 2 * 86400)).fetchall()
    except Exception:
        heads = []
    out["headlines"] = [{"ts": h["ts"], "topic": TOPIC_NAMES[topic_of(h["event"])], "event": h["event"],
                         "dir": h["direction"], "strength": h["strength"], "title": h["title"], "source": h["source"]}
                        for h in heads]
    data = Data(db)
    day = data.window(sym, now, 86400)
    topics: dict[str, dict] = {}
    for k, d, s, top in day:
        x = topics.setdefault(TOPIC_NAMES[top], {"n": 0, "up": 0, "down": 0, "score": 0.0})
        x["n"] += 1
        x["up"] += int(d > 0 and s > 0)
        x["down"] += int(d < 0 and s > 0)
        x["score"] += d * s
    out["topics"] = topics
    try:
        rec = _json.loads(db.get("ta:records") or "null")
    except ValueError:
        rec = None
    if not rec or now - rec.get("ts", 0) > 900:
        rec = {"ts": now, "r": rules.records(db).get("rules", {})}
        db.put("ta:records", _json.dumps(rec, ensure_ascii=False))
    out["book"] = [{"id": r["id"], "name": r["name"], "family": FAMILY.get(r["id"]), "how": r["how"],
                    "signal": r["signal"], "void": r["void"], "source": r["source"],
                    "record": (rec["r"].get(r["id"]) or {}).get("1h")}
                   for r in playbook.RULES if r["area"] == "Xəbər"]
    v = live_voice(db).views(sym, now, "1h").get("xeber", (0.5, ""))
    st = {r["method"]: r for r in judge.stats(db, sym, "1h", "live", ttl=600)}
    hist = {r["method"]: r for r in judge.stats(db, sym, "1h", "history", ttl=600)}
    pick = lambda m: (st.get(m) if (st.get(m) or {}).get("nh") else hist.get(m)) or {}
    out["now"] = {"vote": {"p": v[0], "basis": v[1]},
                  "rules": [{"rule": r, "dir": d, "note": n} for r, d, n in detect(data, sym, now)],
                  "judge": {m: {k: pick(m).get(k) for k in ("nh", "hit_rate", "bar", "status")} for m in ("xeber", "surprise")}}
    from . import reporter
    out["agents"] = reporter.agents_view(db, now)          # Məlumat agentləri: figures found on the web by two brains
    return out


def debug(db: DB, now: float | None = None) -> dict:
    """Why the news voice is quiet (for the diagnostics): the Reader's labels per metal (all, last 7 days, first and
    last time, by direction and strength), the news rules' stored firings, and what the rules see right now."""
    import time as _t
    from . import rules
    rules.ensure(db)
    now = _t.time() if now is None else now
    out: dict = {"metals": {}}
    try:
        r = db.execute("SELECT COUNT(*) n, MIN(ts) f, MAX(ts) l, SUM(ts > ?) w FROM news_ai", (now - 7 * 86400,)).fetchone()
        out["labels"] = {"all": r["n"], "first": r["f"], "last": r["l"], "last_7d": r["w"] or 0}
        dist = db.execute("SELECT direction, strength, COUNT(*) n FROM news_ai WHERE ts > ? GROUP BY direction, strength",
                          (now - 7 * 86400,)).fetchall()
        out["by_direction_strength_7d"] = {f"{x['direction']}:{x['strength']}": x["n"] for x in dist}
        out["no_metal_7d"] = db.execute("SELECT COUNT(*) n FROM news_ai WHERE ts > ? AND (metals IS NULL OR metals='')",
                                        (now - 7 * 86400,)).fetchone()["n"]
    except Exception as e:
        out["labels_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    data = Data(db)
    for m in ("XAU", "XAG", "XPT", "XPD"):
        items = data.by.get(m, [])
        recent = data.window(m, now, 6 * 3600)
        out["metals"][m] = {"labels": len(items), "first": data.first(m), "last_6h": len(recent),
                            "score_6h": round(_score(recent, now), 2), "fires_now": [f[0] for f in detect(data, m, now)],
                            "stored_firings": db.execute("SELECT COUNT(*) n FROM rule_signals WHERE metal=? AND rule LIKE "
                                                         "'NW-%'", (m,)).fetchone()["n"],
                            "replay_mark": db.get(f"nw:ver:{NW_VER}:{m}")}
    return out
