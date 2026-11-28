"""CME həcm və açıq mövqelər (owner 28.11 «hə, başla»): CME's own daily statistics for every gold, silver, platinum and
palladium futures contract — open interest (how many contracts stay open: money coming in or leaving), cleared volume
and the settlement price — through Databento (licensed CME data, the owner's key, the usage-based credit). The CME
site itself blocks automated reading, so this is the permitted way.

Price (free question, 28.11 01:43 NY): one day $0.0031, one year $0.57, five years $1.38. The owner approved five years
and the daily update (28.11 01:47 NY «HA YUKLA»).

PRE-REGISTERED 28.11.2026 01:55 NY, before the download (the rule cannot be fitted to the result):
  Data      the daily open interest of ALL gold futures contracts (CME statistics, summed over the contracts; a roll
            only moves contracts between months, the sum stays), and gold's daily close from our own candles.
  Rule      day D: price change ΔP = close(D) / close(D−1) − 1, open-interest change ΔOI = OI(D) − OI(D−1).
            ΔOI > 0 (new money): gold goes the way it went (continuation) → direction = sign(ΔP);
            ΔOI < 0 (money leaving): the move is running out → direction = −sign(ΔP); ΔP = 0 or ΔOI = 0: none.
  Trade     CME publishes D's open interest the next morning, so the trade starts only at the close of D+1 and ends
            at the close of D+2 (one day); judge.full_cost("XAU", "1d") is taken off.
  Proof     at least 250 days; hits against 50 %, one-sided p < 0.01; the average after cost > 0; both halves of the
            five years positive after cost. Anything less: no proof — the data is shown, it does not steer forecasts.
  Shown, not decisive: the same rule over 5 days; silver, platinum and palladium."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from .db import DB

log = logging.getLogger("tst.dbstats")

HIST = "https://hist.databento.com/v0/"
DATASET = "GLBX.MDP3"
SYMBOLS = "GC.FUT,SI.FUT,PL.FUT,PA.FUT"          # every futures contract of each metal (parent symbology)
WINDOWS = {"1 gün": 1, "1 il": 365, "5 il": 1826}
QUOTE = "dbstats:quote"
APPROVED = {"years": 5, "ceiling_usd": 3.0, "daily_ceiling_usd": 0.05, "by": "sahib 28.11 01:47 NY: «HA YUKLA»"}
METALS = {"XAU": "GC.FUT", "XAG": "SI.FUT", "XPT": "PL.FUT", "XPD": "PA.FUT"}
RESULT, SPENT = "dbstats:result", "dbstats:spent"
SCHEMA = "CREATE TABLE IF NOT EXISTS cme_oi (symbol TEXT NOT NULL, d TEXT NOT NULL, oi INTEGER NOT NULL, " \
         "contracts INTEGER, PRIMARY KEY (symbol, d))"
OI_STAT = 9                     # Databento stat_type: open interest
UNDEF_Q, UNDEF_T = 2147483647, 18446744073709551615
MIN_DAYS, P_BAR = 250, 0.01


async def quote(db: DB, keys, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    key = ((keys.get("databento") if keys is not None else None) or {}).get("key")
    if not key:
        out = {"ts": now, "ok": False, "msg": "Databento açarı yoxdur"}
        db.put(QUOTE, json.dumps(out, ensure_ascii=False))
        return out
    end = (datetime.fromtimestamp(now, timezone.utc) - timedelta(days=2)).date()
    costs, errors = {}, []
    async with httpx.AsyncClient(timeout=30) as c:
        for name, days in WINDOWS.items():
            params = {"dataset": DATASET, "symbols": SYMBOLS, "stype_in": "parent", "schema": "statistics",
                      "start": (end - timedelta(days=days)).isoformat(), "end": end.isoformat()}
            try:
                r = await c.get(HIST + "metadata.get_cost", params=params, auth=(key, ""))
                if r.status_code == 200:
                    costs[name] = round(float(r.json()), 4)
                else:
                    errors.append(f"{name}: HTTP {r.status_code} {r.text[:160]}")
            except (httpx.HTTPError, ValueError) as e:
                errors.append(f"{name}: {type(e).__name__}")
    out = {"ts": now, "ok": bool(costs), "symbols": SYMBOLS, "schema": "statistics", "end": end.isoformat(),
           "cost_usd": costs, "errors": errors}
    db.put(QUOTE, json.dumps(out, ensure_ascii=False))
    return out


def _cost(key: str, symbol: str, start: str, end: str) -> float:
    r = httpx.get(HIST + "metadata.get_cost", params={"dataset": DATASET, "symbols": symbol, "stype_in": "parent",
                                                      "schema": "statistics", "start": start, "end": end},
                  auth=(key, ""), timeout=30)
    r.raise_for_status()
    return float(r.json())


def parse_oi(lines) -> dict[str, tuple[int, int]]:
    """CSV statistics → {day: (open interest summed over contracts, contracts)}; the last record of each contract and
    day counts, a delete removes it."""
    cols = None
    per: dict[str, dict[int, int]] = {}
    for line in lines:
        if not line:
            continue
        if cols is None:
            head = line.split(",")
            cols = {k: head.index(k) for k in ("ts_event", "instrument_id", "ts_ref", "quantity", "stat_type",
                                                "update_action")}
            continue
        f = line.split(",")
        try:
            if int(f[cols["stat_type"]]) != OI_STAT:
                continue
            q, ref = int(f[cols["quantity"]]), int(f[cols["ts_ref"]] or UNDEF_T)
            t = ref if ref != UNDEF_T else int(f[cols["ts_event"]])
            day = datetime.fromtimestamp(t / 1e9, timezone.utc).strftime("%Y-%m-%d")
            inst = int(f[cols["instrument_id"]])
        except (ValueError, IndexError):
            continue
        if f[cols["update_action"]].strip() in ("2", "D"):
            per.get(day, {}).pop(inst, None)
        elif q != UNDEF_Q and q >= 0:
            per.setdefault(day, {})[inst] = q
    return {d: (sum(v.values()), len(v)) for d, v in per.items() if v}


def _download(key: str, symbol: str, start: str, end: str) -> dict[str, tuple[int, int]]:
    params = {"dataset": DATASET, "symbols": symbol, "stype_in": "parent", "schema": "statistics", "start": start,
              "end": end, "encoding": "csv", "compression": "none", "pretty_px": "true", "pretty_ts": "false"}
    with httpx.Client(timeout=httpx.Timeout(60, read=900)) as c:
        with c.stream("POST", HIST + "timeseries.get_range", data=params, auth=(key, "")) as r:
            if r.status_code != 200:
                r.read()
                raise RuntimeError(f"HTTP {r.status_code} {r.text[:160]}")
            return parse_oi(r.iter_lines())


def load(db: DB, key: str, now: float | None = None) -> dict:
    """First run: five years (owner-approved, ceiling APPROVED['ceiling_usd']); after that once a day the days since
    the last stored one (a call costing more than daily_ceiling_usd is not made). Runs in a thread."""
    now = time.time() if now is None else now
    db.script(SCHEMA)
    end = (datetime.fromtimestamp(now, timezone.utc) - timedelta(days=1)).date()
    spent = float(db.get(SPENT) or 0)
    out = {"ts": now, "metals": {}}

    def buy(sym, parent, a, b, ceiling):
        nonlocal spent
        usd = _cost(key, parent, a, b)
        if usd > ceiling:
            return f"dayandı: {usd:.4f} $ > tavan {ceiling} $"
        days = _download(key, parent, a, b)
        db.executemany("INSERT OR REPLACE INTO cme_oi(symbol, d, oi, contracts) VALUES(?,?,?,?)",
                       [(sym, d, v[0], v[1]) for d, v in days.items()])
        spent += usd
        db.put(SPENT, f"{spent:.4f}")
        return f"{len(days)} gün, {usd:.4f} $"

    for sym, parent in METALS.items():
        # the five years go year by year (28.11 03:29: one five-year request timed out before Databento started
        # sending); each year is recorded on its own, so a cut run repeats only the year it was in, and a stored year
        # is never bought again. With all five stored, only the days since the last stored one, once a day.
        if not db.get(f"dbstats:hist:{sym}"):
            notes = []
            for k in range(APPROVED["years"], 0, -1):
                a = (end - timedelta(days=365 * k + (1 if k == APPROVED["years"] else 0))).isoformat()
                b = (end - timedelta(days=365 * (k - 1))).isoformat()
                if db.get(f"dbstats:chunk:{sym}:{a}"):
                    continue
                note = buy(sym, parent, a, b, APPROVED["ceiling_usd"] / APPROVED["years"] + 0.5)
                notes.append(f"{a}→{b}: {note}")
                if note.startswith("dayandı"):
                    break
                db.put(f"dbstats:chunk:{sym}:{a}", note)
            else:
                db.put(f"dbstats:hist:{sym}", str(now))
            out["metals"][sym] = "; ".join(notes) or "5 il artıq yüklənib"
            continue
        last = db.execute("SELECT MAX(d) d FROM cme_oi WHERE symbol=?", (sym,)).fetchone()["d"]
        if last and last < end.isoformat():
            out["metals"][sym] = buy(sym, parent, last, end.isoformat(), APPROVED["daily_ceiling_usd"])
    out["spent_usd_total"] = round(spent, 4)
    db.put("dbstats:last_load", json.dumps(out, ensure_ascii=False))
    return out


def evaluate(db: DB, symbol: str = "XAU", hold: int = 1) -> dict:
    """The pre-registered rule over every day that has both open interest and gold's close."""
    from . import judge
    db.script(SCHEMA)
    oi = {r["d"]: r["oi"] for r in db.execute("SELECT d, oi FROM cme_oi WHERE symbol=? ORDER BY d", (symbol,))}
    px = [(datetime.fromtimestamp(r["t"], timezone.utc).strftime("%Y-%m-%d"), r["c"]) for r in db.execute(
        "SELECT t, c FROM candles WHERE symbol=? AND tf='1d' ORDER BY t", (symbol,))]
    cost = judge.full_cost(symbol, "1d") * hold
    rows = []
    for i in range(1, len(px) - 1 - hold):
        d, d0 = px[i][0], px[i - 1][0]
        if d not in oi or d0 not in oi:
            continue
        dp, doi = px[i][1] / px[i - 1][1] - 1, oi[d] - oi[d0]
        if dp == 0 or doi == 0:
            continue
        way = (1 if dp > 0 else -1) * (1 if doi > 0 else -1)
        entry, exit_ = px[i + 1][1], px[i + 1 + hold][1]
        rows.append((d, (exit_ / entry - 1) * way))
    n = len(rows)
    hits = sum(1 for _, r in rows if r > 0)
    net = [r - cost for _, r in rows]
    half = n // 2
    halves = [sum(net[:half]) / half if half else None, sum(net[half:]) / (n - half) if n - half else None]
    if n < MIN_DAYS:
        status, p = "az", None
    else:
        p = judge._p_one_sided(hits, n, 0.5)
        status = "sübut" if p < P_BAR and sum(net) > 0 and all(h is not None and h > 0 for h in halves) else "yox"
    return {"symbol": symbol, "hold_days": hold, "n": n, "need": MIN_DAYS, "first": rows[0][0] if rows else None,
            "last": rows[-1][0] if rows else None, "hit_rate": round(hits / n, 4) if n else None,
            "net_avg_pct": round(sum(net) / n * 100, 4) if n else None, "p": p, "status": status,
            "halves_net_pct": [round(h * 100, 4) if h is not None else None for h in halves]}


def latest(db: DB) -> dict:
    db.script(SCHEMA)
    out = {}
    for sym in METALS:
        rows = db.execute("SELECT d, oi FROM cme_oi WHERE symbol=? ORDER BY d DESC LIMIT 21", (sym,)).fetchall()
        if rows:
            out[sym] = {"d": rows[0]["d"], "oi": rows[0]["oi"],
                        "ch_1d": rows[0]["oi"] - rows[1]["oi"] if len(rows) > 1 else None,
                        "ch_20d": rows[0]["oi"] - rows[-1]["oi"] if len(rows) > 20 else None}
    return out


async def run(db: DB, keys) -> None:
    """The free price list once a day; with the owner's approval the five years once, then the new days each day."""
    await asyncio.sleep(45)
    while True:
        try:
            last = json.loads(db.get(QUOTE) or "null") or {}
            if not last.get("ok") or time.time() - float(last.get("ts") or 0) > 86400:
                await quote(db, keys)
            key = ((keys.get("databento") if keys is not None else None) or {}).get("key")
            done = json.loads(db.get("dbstats:last_load") or "null") or {}
            age = time.time() - float(done.get("ts") or 0)
            if APPROVED and key and (age > 20 * 3600 or (done.get("error") and age > 600)):
                await asyncio.to_thread(load, db, key)
                res = {"ts": time.time(), "gold_1d": evaluate(db), "gold_5d_shown": evaluate(db, hold=5),
                       "others_1d_shown": {s: evaluate(db, s) for s in ("XAG", "XPT", "XPD")}}
                db.put(RESULT, json.dumps(res, ensure_ascii=False))
        except Exception as e:      # never takes anything down; the next try is in an hour
            msg = str(e)
            k = ((keys.get("databento") if keys is not None else None) or {}).get("key")
            if k:
                msg = msg.replace(k, "***")
            tries = int((json.loads(db.get("dbstats:last_load") or "null") or {}).get("tries") or 0) + 1
            db.put("dbstats:last_load", json.dumps({"ts": time.time() if tries < 5 else time.time() + 86400,
                                                    "error": msg[:200], "tries": tries}, ensure_ascii=False))
            log.warning("dbstats: %s", msg[:200])
        await asyncio.sleep(600)
