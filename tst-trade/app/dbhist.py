"""Böyük oyunçu sübutu — keçmiş məlumatla (owner 27.11 23:10: «əvvəl sübut olsun, sonra edərik»). Databento's live
right was refused («A live data license is required»); the $125 credit buys history. Before paying $199 a month for the
live feed, the same rule the live feed would use is measured on past trades.

PRE-REGISTERED 27.11.2026 23:15 NY, before any trade history was downloaded (the rule cannot be fitted to the result):

  Data      GLBX.MDP3 trades of gold futures, the most traded contract (GC.v.0), the window the owner approves.
  Big trade a single trade of at least max(20 lots, the 99.9th percentile of the previous 5 000 trade sizes) — the same
            line as the live feed (orderflow.Flow); an ALARM is a trade at least twice that line, at most one per
            15 minutes (also as live). Side = the side that started it (B buy, A sell); trades without a side skipped.
  Trade     entry = the last traded price at the first whole minute after the alarm (time to react); exit = the last
            traded price 15 minutes after entry; buy alarm → long, sell alarm → short.
  Cost      judge.full_cost("XAU") is taken off every trade.
  Proof     at least 100 alarms; hits (moved the alarm's way) against 50 %, one-sided p < 0.01; the average after cost
            > 0; and both halves of the window (first / second half by time) must have a positive average after cost.
            Anything less: no proof → the live licence is not bought.
  Shown, not decisive: the 60-minute result, the count of big trades per day.

This module now only asks Databento what the download would cost (metadata.get_cost: free, nothing is downloaded).
The download and the measurement come after the owner approves the amount."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from .db import DB

log = logging.getLogger("tst.dbhist")

HIST = "https://hist.databento.com/v0/"
DATASET = "GLBX.MDP3"
SYMBOL = "GC.v.0"
WINDOWS = {"1 ay": 30, "3 ay": 91, "6 ay": 182, "12 ay": 365}
QUOTE = "dbhist:quote"
MIN_ALARMS, P_BAR, HOLD_MIN = 100, 0.01, 15
# the owner's «hə» (27.11.2026 23:45 NY, «ha yukla») for the 12-month window priced $32.69 from the $125 credit;
# the download stops before it would spend more than CEILING_USD (asked again before every month)
APPROVED = {"months": 12, "end": "2026-11-26", "ceiling_usd": 35.0, "by": "sahib 27.11 23:45 NY: «ha yukla»"}
RESULT, PROGRESS, MONTH_KEY = "dbhist:result", "dbhist:progress", "dbhist:month:"
BIG_MIN_LOTS, WINDOW, RECALC = 20, 5000, 200
SCHEMA = """CREATE TABLE IF NOT EXISTS dbhist_alarm (ts REAL PRIMARY KEY, side INTEGER, size INTEGER, line REAL,
  entry REAL, exit15 REAL, exit60 REAL, inst INTEGER)"""


async def quote(db: DB, keys, now: float | None = None) -> dict:
    """What would the trades of the last 1 / 3 / 6 / 12 months cost (USD, from the $125 credit)? Stored for diag."""
    now = time.time() if now is None else now
    key = ((keys.get("databento") if keys is not None else None) or {}).get("key")
    if not key:
        out = {"ts": now, "ok": False, "msg": "Databento açarı yoxdur"}
        db.put(QUOTE, json.dumps(out))
        return out
    end = (datetime.fromtimestamp(now, timezone.utc) - timedelta(days=2)).date()    # history is complete up to here
    costs, errors = {}, []
    async with httpx.AsyncClient(timeout=30) as c:
        for name, days in WINDOWS.items():
            params = {"dataset": DATASET, "symbols": SYMBOL, "stype_in": "continuous", "schema": "trades",
                      "start": (end - timedelta(days=days)).isoformat(), "end": end.isoformat()}
            try:
                r = await c.get(HIST + "metadata.get_cost", params=params, auth=(key, ""))
                if r.status_code == 200:
                    costs[name] = round(float(r.json()), 2)
                else:
                    errors.append(f"{name}: HTTP {r.status_code} {r.text[:120]}")
            except (httpx.HTTPError, ValueError) as e:
                errors.append(f"{name}: {type(e).__name__}")
    out = {"ts": now, "ok": bool(costs), "symbol": SYMBOL, "schema": "trades", "end": end.isoformat(),
           "cost_usd": costs, "errors": errors}
    db.put(QUOTE, json.dumps(out, ensure_ascii=False))
    return out


class Study:
    """The pre-registered rule over a stream of trades in time order (one instrument at a time; a roll to the next
    contract is seen by the instrument id and an alarm whose exit lies in another contract is not counted).
    Memory stays small: the last WINDOW sizes and the minute closes of the last ~61 minutes."""

    def __init__(self):
        from collections import deque
        self.sizes = deque(maxlen=WINDOW)
        self.line = float(BIG_MIN_LOTS)
        self.since = 0
        self.last_q = None
        self.cur_min, self.cur_px, self.cur_inst = None, None, None
        self.closes: dict[int, tuple[int, float]] = {}       # minute start -> (instrument, last price)
        self.pending: list[dict] = []
        self.done: list[dict] = []
        self.trades = self.big = 0
        self.days: set = set()

    def _close_minute(self) -> None:
        if self.cur_min is None:
            return
        self.closes[self.cur_min] = (self.cur_inst, self.cur_px)
        for m in [m for m in self.closes if m < self.cur_min - 3700]:
            del self.closes[m]

    def _px_at(self, t: int) -> tuple[int, float] | None:
        """The last traded price before time t (a whole minute): the close of the last minute that had a trade."""
        for m in range(t - 60, t - 3660, -60):
            if m in self.closes:
                return self.closes[m]
        return None

    def _settle(self, now_min: int) -> None:
        keep = []
        for a in self.pending:
            if "entry" not in a and now_min >= a["m0"]:
                e = self._px_at(a["m0"])
                a["entry"], a["inst"] = (e[1], e[0]) if e else (None, None)
            if "exit15" not in a and now_min >= a["m0"] + HOLD_MIN * 60:
                x = self._px_at(a["m0"] + HOLD_MIN * 60)
                a["exit15"] = x[1] if x and x[0] == a.get("inst") else None
            if now_min >= a["m0"] + 3600:
                x = self._px_at(a["m0"] + 3600)
                a["exit60"] = x[1] if x and x[0] == a.get("inst") else None
                self.done.append(a)
            else:
                keep.append(a)
        self.pending = keep

    def add(self, ts: float, inst: int, price: float, size: int, side: str) -> None:
        self.trades += 1
        m = int(ts // 60) * 60
        if m != self.cur_min:
            self._close_minute()
            self._settle(m)
            self.cur_min = m
            if m // 86400 not in self.days:
                self.days.add(m // 86400)
        self.cur_px, self.cur_inst = price, inst
        line = self.line
        self.sizes.append(size)
        self.since += 1
        if self.since >= RECALC and len(self.sizes) >= 1000:       # the line is refreshed every RECALC trades
            xs = sorted(self.sizes)
            self.line = max(float(BIG_MIN_LOTS), float(xs[int(len(xs) * 0.999)]))
            self.since = 0
        if size < line or side not in ("A", "B"):
            return
        self.big += 1
        q = int(ts // 900)
        if size < 2 * line or q == self.last_q:
            return
        self.last_q = q
        self.pending.append({"ts": ts, "side": 1 if side == "B" else -1, "size": size, "line": line,
                             "m0": int(-(-ts // 60) * 60)})

    def finish(self) -> None:
        """End of the whole window: settle what the data covers; an alarm whose 15 minutes run past the last trade
        is dropped (its result is unknown, not guessed)."""
        if self.cur_min is None:
            return
        self._close_minute()
        self._settle(self.cur_min + 60)
        self.done += [a for a in self.pending if a.get("exit15")]
        self.pending = []


def verdict(alarms: list[dict]) -> dict:
    """The pre-registered test on the settled alarms (15 minutes decides, 60 minutes is only shown)."""
    from . import judge
    cost = judge.full_cost("XAU")

    def leg(key):
        rows = sorted((a["ts"], (a[key] / a["entry"] - 1) * a["side"]) for a in alarms
                      if a.get("entry") and a.get(key))
        n = len(rows)
        if not n:
            return {"n": 0}
        hits = sum(1 for _, r in rows if r > 0)
        net = [r - cost for _, r in rows]
        half = n // 2
        h1 = sum(net[:half]) / half if half else None
        h2 = sum(net[half:]) / (n - half) if n - half else None
        return {"n": n, "hit_rate": round(hits / n, 4), "net_avg_pct": round(sum(net) / n * 100, 4),
                "p": judge._p_one_sided(hits, n, 0.5), "halves_net_pct": [round((h or 0) * 100, 4) for h in (h1, h2)],
                "net_all": net}

    m15, m60 = leg("exit15"), leg("exit60")
    n = m15.get("n", 0)
    if n < MIN_ALARMS:
        status = "az"
    else:
        ok = m15["p"] < P_BAR and sum(m15["net_all"]) > 0 and all(h > 0 for h in m15["halves_net_pct"])
        status = "sübut" if ok else "yox"
    for m in (m15, m60):
        m.pop("net_all", None)
    return {"status": status, "need": MIN_ALARMS, "p_bar": P_BAR, "cost_pct": round(cost * 100, 4), "m15": m15,
            "m60_shown_only": m60}


def _months(end: str, n: int) -> list[tuple[str, str]]:
    e = datetime.fromisoformat(end).date()
    s = e - timedelta(days=365)
    edges = [s + timedelta(days=round(365 * k / n)) for k in range(n + 1)]
    return [(edges[k].isoformat(), edges[k + 1].isoformat()) for k in range(n)]


def _cost(key: str, start: str, end: str) -> float:
    r = httpx.get(HIST + "metadata.get_cost", params={"dataset": DATASET, "symbols": SYMBOL, "stype_in": "continuous",
                                                      "schema": "trades", "start": start, "end": end},
                  auth=(key, ""), timeout=30)
    r.raise_for_status()
    return float(r.json())


def _stream_month(key: str, start: str, end: str, study: Study, db: DB, label: str) -> int:
    """Streams one month of trades as CSV (nothing kept on disk) into the study. Returns the lines read."""
    params = {"dataset": DATASET, "symbols": SYMBOL, "stype_in": "continuous", "schema": "trades", "start": start,
              "end": end, "encoding": "csv", "compression": "none", "pretty_px": "true", "pretty_ts": "false"}
    n = 0
    with httpx.Client(timeout=httpx.Timeout(60, read=300)) as c:
        with c.stream("POST", HIST + "timeseries.get_range", data=params, auth=(key, "")) as r:
            # 206: Databento sends the data with a warning (some days' quality is not «available») — still the data
            # (28.11 03:34: a 206 was taken for an error and a paid year was thrown away)
            if r.status_code not in (200, 206):
                r.read()
                raise RuntimeError(f"HTTP {r.status_code} {r.text[:160]}")
            cols = None
            for line in r.iter_lines():
                if not line:
                    continue
                if cols is None:
                    head = line.split(",")
                    cols = (head.index("ts_event"), head.index("instrument_id"), head.index("price"),
                            head.index("size"), head.index("side"))
                    continue
                f = line.split(",")
                try:
                    study.add(int(f[cols[0]]) / 1e9, int(f[cols[1]]), float(f[cols[2]]), int(f[cols[3]]), f[cols[4]])
                except (ValueError, IndexError):
                    continue
                n += 1
                if n % 50000 == 0:
                    time.sleep(0.003)                  # let the site breathe (one worker, one CPU)
                    db.put(PROGRESS, json.dumps({"ts": time.time(), "month": label, "lines": n,
                                                 "alarms": len(study.done) + len(study.pending)}))
    return n


def download_and_measure(db: DB, key: str) -> dict:
    """The owner-approved download (APPROVED), month by month, then the verdict. Runs in a thread."""
    db.script(SCHEMA)
    months = _months(APPROVED["end"], APPROVED["months"])
    spent = sum(float((json.loads(db.get(MONTH_KEY + a) or "null") or {}).get("usd") or 0) for a, _ in months)
    study = Study()                                     # alarms waiting for their exit cross month boundaries
    for k, (a, b) in enumerate(months):
        if db.get(MONTH_KEY + a):
            continue                                    # this month was already paid for and measured
        t0, b0, d0 = study.trades, study.big, len(study.days)
        usd = _cost(key, a, b)
        if spent + usd > APPROVED["ceiling_usd"]:
            out = {"ts": time.time(), "done": False, "stopped": f"tavan: {spent:.2f} + {usd:.2f} > "
                                                                  f"{APPROVED['ceiling_usd']} $ — sahibdən soruşulur"}
            db.put(RESULT, json.dumps(out, ensure_ascii=False))
            return out
        lines = _stream_month(key, a, b, study, db, f"{k + 1}/{len(months)} ({a} → {b})")
        if k == len(months) - 1:
            study.finish()
        for x in study.done:
            db.execute("INSERT OR REPLACE INTO dbhist_alarm VALUES(?,?,?,?,?,?,?,?)",
                       (x["ts"], x["side"], x["size"], x["line"], x.get("entry"), x.get("exit15"), x.get("exit60"),
                        x.get("inst")))
        db.put(MONTH_KEY + a, json.dumps({"usd": usd, "lines": lines, "trades": study.trades - t0,
                                          "big": study.big - b0, "days": len(study.days) - d0, "ts": time.time()}))
        spent += usd
        study.done = []
    alarms = [dict(r) for r in db.execute("SELECT * FROM dbhist_alarm ORDER BY ts").fetchall()]
    per = [json.loads(db.get(MONTH_KEY + a) or "{}") for a, _ in months]
    trades, big, days = (sum(int(p.get(k) or 0) for p in per) for k in ("trades", "big", "days"))
    out = {"ts": time.time(), "done": True, "window": [months[0][0], months[-1][1]], "spent_usd": round(spent, 2),
           "trades": trades, "big_trades": big, "big_per_day": round(big / days, 1) if days else None,
           "alarms": len(alarms), **verdict(alarms)}
    db.put(RESULT, json.dumps(out, ensure_ascii=False))
    return out


async def run(db: DB, keys) -> None:
    """Once after a start (and once a day): the price list. With the owner's approval (APPROVED) the download and the
    measurement run once; a finished result is never downloaded again."""
    while True:
        try:
            last = json.loads(db.get(QUOTE) or "null") or {}
            if not last.get("ok") or time.time() - float(last.get("ts") or 0) > 86400:
                await quote(db, keys)
            res = json.loads(db.get(RESULT) or "null") or {}
            key = ((keys.get("databento") if keys is not None else None) or {}).get("key")
            tries = int(res.get("attempts") or 0)
            if APPROVED and key and not res.get("done") and not res.get("stopped") and tries < 3:
                try:
                    await asyncio.to_thread(download_and_measure, db, key)
                except Exception as e:      # at most 3 tries: a lasting error must not keep paying for half months
                    msg = str(e).replace(key, "***")[:200]
                    db.put(RESULT, json.dumps({"ts": time.time(), "done": False, "attempts": tries + 1,
                                               "error": f"{type(e).__name__}: {msg}"}, ensure_ascii=False))
                    log.warning("dbhist download: %s", msg)
        except Exception as e:      # a price question must never take anything down
            log.warning("dbhist: %s", e)
        await asyncio.sleep(3600)
