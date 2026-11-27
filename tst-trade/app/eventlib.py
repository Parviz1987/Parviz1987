"""Hadisələr kitabxanası (owner 2026-11-27: «Kitabxananı qur»): the past US releases and Fed decisions, each with what
was known at that moment and how the metals moved after it, so the brains and the blocks can ask «what happened the
other times this happened?» — and the library grows by itself with every new release.

Sources (all public, no scraping): the FRED release dates (CPI, payrolls, GDP, PCE; kv «calendar:history»), ALFRED's
FIRST published values of those figures (table macro_first, never a later revision), the Fed's own meeting days and
the upper target rate (DFEDTARU), and for new releases the calendar's economists' estimate (table releases).

Point-in-time rule: an event stores only what was public at its moment. Before the calendar has an estimate, the
«surprise» is the first published change against the mean of the three changes before it (labelled «trend əvəzi»,
a stand-in for the consensus, not the consensus). A move is used only once its horizon has ended before the question.

Kölgə sınağı: every event is predicted walk-forward from the earlier events alone (their 1-week move finished before
it); the analogs reach the brains only for a metal and horizon where that test beat the market's own lean after the
full cost (Bonferroni over 4 metals x 2 horizons)."""
from __future__ import annotations

import json
import math
import time
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone

from .db import DB

EV_VER = "2026-11-27.2"   # .2: the Fed target from plain observations (never revised)
SERIES = {"CPI": "CPIAUCSL", "Employment Situation": "PAYEMS", "Personal Income and Outlays": "PCEPI",
          "GDP": "GDPC1"}
FIRST_SERIES = tuple(SERIES.values()) + ("DFEDTARU",)
NOT_REVISED = ("DFEDTARU",)
MIN_LAG = {"CPIAUCSL": 32, "PAYEMS": 28, "PCEPI": 45, "GDPC1": 80}   # days from the period's first day to its release
NAMES = {"CPI": "CPI (inflyasiya)", "Employment Situation": "NFP (iş yerləri)", "GDP": "ÜDM",
         "Personal Income and Outlays": "PCE (inflyasiya)", "FOMC": "Fed qərarı"}
GOLD_SIGN = {"CPI": -1, "Employment Situation": -1, "GDP": -1, "Personal Income and Outlays": -1, "FOMC": -1}
CALENDAR_MATCH = {"CPI": ("cpi", "consumer price"), "Employment Situation": ("non-farm", "nonfarm", "non farm"),
                  "GDP": ("gdp",), "Personal Income and Outlays": ("pce",), "FOMC": ("federal funds", "interest rate")}
NEAR = 0.5                      # |z| below this: «gözləntiyə yaxın»
MIN_ANALOGS = 8
HORIZONS = ("1d", "1w")
METALS = ("XAU", "XAG", "XPT", "XPD")
KEY_TEST = "eventlib:test"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ev_lib (id TEXT PRIMARY KEY, kind TEXT NOT NULL, t REAL NOT NULL, period TEXT,
  value REAL, change REAL, base REAL, surprise REAL, cat TEXT NOT NULL, basis TEXT NOT NULL, usd_trend INTEGER,
  note TEXT);
CREATE INDEX IF NOT EXISTS ev_lib_t ON ev_lib(t);
CREATE TABLE IF NOT EXISTS ev_move (id TEXT NOT NULL, symbol TEXT NOT NULL, h TEXT NOT NULL, ret REAL NOT NULL,
  done_t REAL NOT NULL, trend INTEGER, PRIMARY KEY (id, symbol, h));
"""


def ensure(db: DB) -> None:
    db.script(SCHEMA)


# ---------------------------------------------------------------- building the events

def _first(db: DB, sid: str) -> tuple[list[str], list[float]]:
    try:
        rows = db.execute("SELECT d, v FROM macro_first WHERE series=? ORDER BY d", (sid,)).fetchall()
    except Exception:
        return [], []
    return [r["d"] for r in rows], [r["v"] for r in rows]


def _day(d: str) -> float:
    return datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()


def change_of(kind: str, vals: list[float], i: int) -> float | None:
    """The figure the market reads: monthly % for prices, the jobs added (thousands), quarterly % for GDP."""
    if i < 1 or vals[i - 1] == 0:
        return None
    if kind == "Employment Situation":
        return vals[i] - vals[i - 1]
    return (vals[i] / vals[i - 1] - 1) * 100


def releases_of(kind: str, dates: list[float], obs_d: list[str], obs_v: list[float]) -> list[dict]:
    """Each release date -> the newest period it published for the first time (the period's first day at least
    MIN_LAG days before), once per period (GDP's second and third estimates are not new events)."""
    sid = SERIES[kind]
    starts = [_day(d) for d in obs_d]
    seen, out = set(), []
    for rt in sorted(dates):
        k = bisect_right(starts, rt - MIN_LAG[sid] * 86400) - 1
        if k < 0 or k in seen:
            continue
        seen.add(k)
        ch = change_of(kind, obs_v, k)
        if ch is None:
            continue
        prev = [change_of(kind, obs_v, j) for j in range(k - 3, k)]
        prev = [p for p in prev if p is not None]
        if len(prev) < 3:
            continue
        out.append({"kind": kind, "t": rt, "period": obs_d[k], "value": obs_v[k], "change": ch,
                    "base": sum(prev) / 3})
    return out


def _zscore(rows: list[dict]) -> None:
    """Surprise = (change - base) / spread of the earlier surprises (24 before it; only the past is used)."""
    raw = []
    for r in rows:
        s = r["change"] - r["base"]
        past = raw[-24:]
        if len(past) >= 8:
            mu = sum(past) / len(past)
            sd = math.sqrt(sum((x - mu) ** 2 for x in past) / (len(past) - 1)) or 1e-9
            r["surprise"] = s / sd
        else:
            r["surprise"] = None
        raw.append(s)


def category(z: float | None) -> str | None:
    if z is None:
        return None
    return "yuxarı" if z > NEAR else "aşağı" if z < -NEAR else "yaxın"


def fomc_events(db: DB, days: list[float]) -> list[dict]:
    d, v = _first(db, "DFEDTARU")
    if not d:
        return []
    ts = [_day(x) for x in d]
    out = []
    for t in sorted(days):
        a = bisect_right(ts, t - 86400) - 1          # the target the day before
        b = bisect_right(ts, t + 2 * 86400) - 1      # the target set by the decision (effective the next day)
        if a < 0 or b < 0 or b <= a or ts[b] > time.time():
            continue
        ch = round((v[b] - v[a]) * 100)               # basis points
        cat = "yuxarı" if ch > 0 else "aşağı" if ch < 0 else "yaxın"
        out.append({"kind": "FOMC", "t": t, "period": d[b], "value": v[b],
                    "change": ch, "base": 0.0, "surprise": None, "cat": cat, "basis": "qərar"})
    return out


def _calendar_estimates(db: DB) -> dict[tuple[str, int], float]:
    """(kind, day) -> the economists' estimate minus the actual is known for new releases (FMP calendar)."""
    out = {}
    try:
        rows = db.execute("SELECT ts, event, estimate, actual FROM releases WHERE estimate IS NOT NULL AND actual IS "
                          "NOT NULL").fetchall()
    except Exception:
        return out
    for r in rows:
        ev = str(r["event"]).lower()
        for kind, keys in CALENDAR_MATCH.items():
            if kind != "FOMC" and any(k in ev for k in keys) and "core" not in ev and "yoy" not in ev:
                out.setdefault((kind, int(r["ts"] // 86400)), r["actual"] - r["estimate"])
    return out


def _trend(closes_t: list[float], closes: list[float], t: float, n: int = 20) -> int | None:
    k = bisect_left(closes_t, t - 86400) - 1          # the last daily candle finished before the event's day
    if k < n:
        return None
    r = closes[k] / closes[k - n] - 1
    return 1 if r > 0.005 else -1 if r < -0.005 else 0


def _daily(db: DB, sym: str) -> tuple[list[float], list[float]]:
    rows = db.execute("SELECT t, c FROM candles WHERE symbol=? AND tf='1d' ORDER BY t", (sym,)).fetchall()
    return [float(r["t"]) for r in rows], [r["c"] for r in rows]


def moves(ts: list[float], cs: list[float], t: float) -> dict[str, tuple[float, float]]:
    """From the close before the event's day: to the close of the event's day (1d) and 5 trading days on (1w)."""
    out = {}
    k = bisect_left(ts, t - 86400 + 1)               # first candle that is not finished before the event
    if k < 1 or k >= len(ts) or ts[k] > t:
        return out
    base = cs[k - 1]
    out["1d"] = (cs[k] / base - 1, ts[k] + 86400)
    if k + 4 < len(ts):
        out["1w"] = (cs[k + 4] / base - 1, ts[k + 4] + 86400)
    return out


def build(db: DB, now: float | None = None) -> dict:
    """Rebuild the library from the stored sources (idempotent, once a day)."""
    ensure(db)
    now = time.time() if now is None else now
    try:
        hist = json.loads(db.get("calendar:history") or "{}")
    except ValueError:
        hist = {}
    est = _calendar_estimates(db)
    rows: list[dict] = []
    for kind, sid in SERIES.items():
        od, ov = _first(db, sid)
        evs = releases_of(kind, [t for t in hist.get(kind, []) if t < now], od, ov)
        _zscore(evs)
        for e in evs:
            e["cat"], e["basis"] = category(e["surprise"]), "trend əvəzi"
            cal = est.get((kind, int(e["t"] // 86400)))
            if cal is not None:                        # the real consensus, where the calendar has it
                e["cat"] = "yuxarı" if cal > 0 else "aşağı" if cal < 0 else "yaxın"
                e["basis"] = "ekspert gözləntisi"
        rows += [e for e in evs if e["cat"]]
    rows += fomc_events(db, [t for t in hist.get("FOMC", []) if t < now])
    dt, dc = _daily(db, "DXY")
    daily = {s: _daily(db, s) for s in METALS}
    lib, mv = [], []
    for e in rows:
        eid = f"{e['kind']}:{int(e['t'])}"
        lib.append((eid, e["kind"], e["t"], e["period"], e["value"], e["change"], e["base"], e.get("surprise"),
                    e["cat"], e["basis"], _trend(dt, dc, e["t"]) if dt else None, None))
        for s, (ts, cs) in daily.items():
            tr = _trend(ts, cs, e["t"])
            for h, (ret, done) in moves(ts, cs, e["t"]).items():
                if done <= now:
                    mv.append((eid, s, h, ret, done, tr))
    db.execute("DELETE FROM ev_lib")
    db.execute("DELETE FROM ev_move")
    db.executemany("INSERT INTO ev_lib VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", lib)
    db.executemany("INSERT INTO ev_move VALUES(?,?,?,?,?,?)", mv)
    res = {"computed": now, "events": len(lib), "moves": len(mv),
           "by_kind": {k: sum(1 for x in lib if x[1] == k) for k in NAMES},
           "first": min((x[2] for x in lib), default=None)}
    try:
        res["fetch"] = json.loads(db.get("eventlib:fetch") or "null")
    except ValueError:
        res["fetch"] = None
    res["test"] = shadow_test(db, now)
    db.put("eventlib:state", json.dumps(res, ensure_ascii=False))
    return res


# ---------------------------------------------------------------- the analog tool

def _events(db: DB) -> list[dict]:
    return [dict(r) for r in db.execute("SELECT * FROM ev_lib ORDER BY t").fetchall()]


def _moves_of(db: DB, symbol: str, h: str) -> dict[str, tuple[float, float, int | None]]:
    return {r["id"]: (r["ret"], r["done_t"], r["trend"]) for r in db.execute(
        "SELECT id, ret, done_t, trend FROM ev_move WHERE symbol=? AND h=?", (symbol, h)).fetchall()}


def analogs(evs: list[dict], mv: dict, kind: str, cat: str, usd: int | None, before: float) -> list[float]:
    """The moves of the earlier events of the same kind and outcome (same dollar trend when enough of them), whose
    move had finished before `before`."""
    base = [e for e in evs if e["kind"] == kind and e["cat"] == cat and e["id"] in mv and mv[e["id"]][1] <= before]
    same = [e for e in base if usd is not None and e["usd_trend"] == usd]
    pick = same if len(same) >= MIN_ANALOGS else base
    return [mv[e["id"]][0] for e in pick]


def summary(rets: list[float]) -> dict | None:
    if len(rets) < MIN_ANALOGS:
        return None
    up = sum(r > 0 for r in rets) / len(rets)
    return {"n": len(rets), "up_share": round(up, 3), "mean_pct": round(100 * sum(rets) / len(rets), 3),
            "median_pct": round(100 * sorted(rets)[len(rets) // 2], 3)}


def shadow_test(db: DB, now: float | None = None) -> dict:
    """Walk-forward: each event's direction from its earlier analogs only; against the market's own lean after the
    full cost. Pass = enough decided cases, net positive, t >= 2.5 (Bonferroni 8 cells at 5 %), hits above the lean."""
    from . import judge
    now = time.time() if now is None else now
    evs = _events(db)
    out: dict = {}
    for s in METALS:
        for h in HORIZONS:
            mv = _moves_of(db, s, h)
            cost = judge.full_cost(s, h)
            nets, hits, ups = [], 0, []
            for e in evs:
                if e["id"] not in mv:
                    continue
                y = mv[e["id"]][0]
                sm = summary(analogs(evs, mv, e["kind"], e["cat"], e["usd_trend"], e["t"]))
                if sm and abs(sm["up_share"] - 0.5) >= 0.1:
                    d = 1 if sm["up_share"] > 0.5 else -1
                    nets.append(d * y - cost)
                    hits += (d * y) > 0
                    ups.append(int(y > 0))
            n = len(nets)
            mu = sum(nets) / n if n else 0.0
            sd = math.sqrt(sum((x - mu) ** 2 for x in nets) / (n - 1)) if n > 1 else 0.0
            t = mu / (sd / math.sqrt(n)) if sd > 0 else 0.0
            lean = max(sum(ups) / n, 1 - sum(ups) / n) if n else 0.5
            hit = hits / n if n else None
            ok = n >= 60 and mu > 0 and t >= 2.5 and hit is not None and hit > lean
            out[f"{s}:{h}"] = {"n": n, "hit": round(hit, 3) if hit is not None else None, "lean": round(lean, 3),
                               "net_avg_pct": round(100 * mu, 3), "t": round(t, 2), "passed": ok}
    res = {"computed": now, "cells": out, "passed": sorted(k for k, v in out.items() if v["passed"])}
    db.put(KEY_TEST, json.dumps(res, ensure_ascii=False))
    return res


def _kind_of(title: str) -> str | None:
    t = title.lower()
    for kind, keys in CALENDAR_MATCH.items():
        if any(k in t for k in keys) and "core" not in t:
            return kind
    return None


def for_brains(db: DB, upcoming: list[dict], released: list[dict], now: float | None = None) -> list[dict]:
    """The analogs the brains may read: for an upcoming or just-released event, per outcome, only in the cells that
    passed the shadow test. Each line says where it comes from; the brain reads the numbers, never invents them."""
    now = time.time() if now is None else now
    try:
        passed = set(json.loads(db.get(KEY_TEST) or "{}").get("passed") or [])
        ensure(db)
        evs = _events(db)
    except Exception:
        return []
    if not passed or not evs:
        return []
    dt, dc = _daily(db, "DXY")
    usd = _trend(dt, dc, now) if dt else None
    out = []
    items = [(r.get("title") or r.get("event") or "", None) for r in upcoming[:8]]
    items += [(r.get("event") or "", (r.get("actual"), r.get("estimate"))) for r in released[:6]]
    for title, fact in items:
        kind = _kind_of(str(title))
        if kind is None:
            continue
        cats = ("yuxarı", "yaxın", "aşağı")
        if fact and fact[0] is not None and fact[1] is not None:
            cats = ("yuxarı" if fact[0] > fact[1] else "aşağı" if fact[0] < fact[1] else "yaxın",)
        for cell in sorted(passed):
            s, h = cell.split(":")
            mv = _moves_of(db, s, h)
            for cat in cats:
                sm = summary(analogs(evs, mv, kind, cat, usd, now))
                if sm:
                    out.append({"event": title, "kind": NAMES[kind], "outcome_vs_expected": cat, "metal": s,
                                "horizon": h, **sm, "source": "hadisələr kitabxanası (keçmiş hallar)"})
    return out[:12]


def view(db: DB, symbol: str = "XAU") -> dict:
    """For the page and the diagnostics: the library's size, the shadow test, and the analog table per kind."""
    try:
        st = json.loads(db.get("eventlib:state") or "null")
        ensure(db)
        evs = _events(db)
    except Exception:
        return {"state": None}
    table = []
    for h in HORIZONS:
        mv = _moves_of(db, symbol, h)
        for kind in NAMES:
            for cat in ("yuxarı", "yaxın", "aşağı"):
                rets = [mv[e["id"]][0] for e in evs if e["kind"] == kind and e["cat"] == cat and e["id"] in mv]
                sm = summary(rets)
                if sm:
                    table.append({"kind": NAMES[kind], "outcome": cat, "horizon": h, **sm})
    return {"state": st, "symbol": symbol, "table": table,
            "last": [{k: e[k] for k in ("kind", "t", "cat", "basis", "change", "surprise")} for e in evs[-5:]]}
