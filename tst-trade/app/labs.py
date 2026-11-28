"""Laboratoriyalar (owner 28.11 04:00: «kiçik-kiçik fərqli yollarla, laboratoriyalar şəklində, keçmişlə bağlı ... sən
özün qərarlaşdır»). Each lab asks ONE question about the past, with a rule written down BEFORE its result is computed
(the text below and the git history are the proof), tested by code on history after the full cost, and shown with
the same verdict words everywhere: «az» (too few cases), «yox» (no proof), «sübut». A lab with proof does not steer
forecasts by itself: it next runs as a live shadow, and only then may the Judge give it a voice. Many labs mean many
chances of a lucky pass, so each lab's bar is strict (p < 0.01) and both halves of its history must agree.

PRE-REGISTERED 28.11.2026 04:00 NY (git 3f4cdc5), before any of these three results was computed:

L1  Fed sürprizi — the surprise, not the decision: on a Fed decision day D the 2-year Treasury yield's change
    (DGS2(D) − DGS2(D−1)) is the market's own reading of how hawkish it was. |change| < 5 bp: no signal. Up (hawkish)
    → gold down; down (dovish) → gold up. Trade: from the close of D+1 to the close 5 trading days later
    (the drift after the first reaction), cost judge.full_cost("XAU", "1w"). Proof: ≥ 20 events.
L2  ABŞ rəqəmləri sürprizi — CPI and payrolls (the event library's categories «yuxarı» / «aşağı» against the
    expectation, point-in-time): a stronger figure is hawkish → gold down, a weaker one → up. Trade: from the close of
    the release day to the close 4 trading days later (does the first reaction keep going?), cost
    judge.full_cost("XAU", "1w"). Proof: ≥ 100 events. (The library's own analog test, seen 27.11, is a different
    rule; this fixed-sign drift rule is new.)
L3  İri fondlar həddə (CFTC COT) — managed money's net position against its own previous 156 weeks: at or above the
    90th percentile (midrank: equal weeks count half) the crowd of funds is full → gold down; at or below the 10th → up. The report for Tuesday d is
    public on Friday d+3; the trade starts at the close of the first trading day from d+6 and lasts 20 trading days;
    a new trade only after the last one ended (no overlap); cost judge.full_cost("XAU", "1mo"). Proof: ≥ 15 trades.
Every lab: hits against 50 % one-sided p < 0.01; the average after cost > 0; both halves by time positive after cost.
Silver is shown for each lab, it does not decide."""
from __future__ import annotations

import json
import time
from bisect import bisect_left
from datetime import datetime, timedelta, timezone

from .db import DB

P_BAR = 0.01


def _rows(db: DB, sql: str, args: tuple = ()) -> list:
    try:
        return db.execute(sql, args).fetchall()
    except Exception:
        return []


def daily(db: DB, sym: str) -> tuple[list[str], list[float]]:
    rows = _rows(db, "SELECT t, c FROM candles WHERE symbol=? AND tf='1d' ORDER BY t", (sym,))
    return [datetime.fromtimestamp(r["t"], timezone.utc).strftime("%Y-%m-%d") for r in rows], [r["c"] for r in rows]


def verdict(trades: list[tuple[str, float]], cost: float, min_n: int) -> dict:
    """trades: (date, signed return) in time order."""
    from . import judge
    n = len(trades)
    hits = sum(1 for _, r in trades if r > 0)
    net = [r - cost for _, r in trades]
    half = n // 2
    halves = [sum(net[:half]) / half if half else None, sum(net[half:]) / (n - half) if n - half else None]
    if n < min_n:
        status, p = "az", None
    else:
        p = judge._p_one_sided(hits, n, 0.5)
        status = "sübut" if p < P_BAR and sum(net) > 0 and all(h is not None and h > 0 for h in halves) else "yox"
    return {"n": n, "need": min_n, "first": trades[0][0] if trades else None, "last": trades[-1][0] if trades else None,
            "hit_rate": round(hits / n, 4) if n else None, "net_avg_pct": round(sum(net) / n * 100, 4) if n else None,
            "p": p, "status": status, "cost_pct": round(cost * 100, 4),
            "halves_net_pct": [round(h * 100, 4) if h is not None else None for h in halves]}


def _hold(dates: list[str], closes: list[float], start_date: str, days: int) -> tuple[str, float] | None:
    """From the close of the first trading day on or after start_date to the close `days` trading days later."""
    k = bisect_left(dates, start_date)
    if k + days >= len(dates):
        return None
    # a start before the price history (or in a gap) is not moved to the first candle: no trade (28.11)
    if (datetime.fromisoformat(dates[k]) - datetime.fromisoformat(start_date[:10])).days > 7:
        return None
    return dates[k], closes[k + days] / closes[k] - 1


def lab_fed(db: DB, sym: str = "XAU") -> dict:
    from . import judge
    dates, closes = daily(db, sym)
    y2 = {r["d"]: r["v"] for r in _rows(db, "SELECT d, v FROM macro WHERE series='DGS2' ORDER BY d")}
    yd = sorted(y2)
    trades = []
    for r in _rows(db, "SELECT t FROM ev_lib WHERE kind='FOMC' ORDER BY t"):
        d = datetime.fromtimestamp(r["t"], timezone.utc).strftime("%Y-%m-%d")
        if d not in y2:
            continue
        i = yd.index(d)
        if i < 1:
            continue
        ch = (y2[d] - y2[yd[i - 1]]) * 100
        if abs(ch) < 5:
            continue
        way = -1 if ch > 0 else 1
        nxt = (datetime.fromisoformat(d) + timedelta(days=1)).strftime("%Y-%m-%d")
        h = _hold(dates, closes, nxt, 5)
        if h:
            trades.append((h[0], h[1] * way))
    return verdict(trades, judge.full_cost(sym, "1w"), 20)


def lab_data(db: DB, sym: str = "XAU") -> dict:
    from . import judge
    from .eventlib import GOLD_SIGN
    dates, closes = daily(db, sym)
    trades = []
    for r in _rows(db, "SELECT kind, t, cat FROM ev_lib WHERE kind IN ('CPI', 'Employment Situation') "
                       "AND cat IN ('yuxarı', 'aşağı') ORDER BY t"):
        way = GOLD_SIGN[r["kind"]] * (1 if r["cat"] == "yuxarı" else -1)
        d = datetime.fromtimestamp(r["t"], timezone.utc).strftime("%Y-%m-%d")
        h = _hold(dates, closes, d, 4)
        if h and h[0] == d:                     # the release day itself must be a trading day in the candles
            trades.append((h[0], h[1] * way))
    return verdict(trades, judge.full_cost(sym, "1w"), 100)


COT_HIST = "CREATE TABLE IF NOT EXISTS cot_hist (symbol TEXT NOT NULL, d TEXT NOT NULL, oi REAL, mm_long REAL, " \
           "mm_short REAL, pm_long REAL, pm_short REAL, PRIMARY KEY (symbol, d))"


async def refresh_cot(db: DB) -> int:
    """The labs' own deep COT history (CFTC open data from 2006, one request a day). Kept apart from the Fundamental
    block's «cot» table (about three years), so the block's measured rules do not change (28.11: L3 had 0 cases —
    three years of COT are used up by its own 156-week look-back)."""
    import httpx
    from .feeds import COT_CODES, COT_URL, parse_cot
    db.script(COT_HIST)
    codes = ",".join(f"'{c}'" for c in COT_CODES)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(COT_URL, params={
            "$select": "cftc_contract_market_code,report_date_as_yyyy_mm_dd,open_interest_all,"
                       "m_money_positions_long_all,m_money_positions_short_all,prod_merc_positions_long,"
                       "prod_merc_positions_short",
            "$where": f"cftc_contract_market_code in({codes})", "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": "5000"})
    r.raise_for_status()
    rows = parse_cot(r.content)
    db.executemany("INSERT OR REPLACE INTO cot_hist VALUES(?,?,?,?,?,?,?)", rows)
    return len(rows)


async def run(db: DB) -> None:
    import asyncio
    import logging
    await asyncio.sleep(90)
    while True:
        try:
            n = await refresh_cot(db)
            db.put("labs:cot_hist", json.dumps({"ts": time.time(), "rows": n}))
        except Exception as e:
            db.put("labs:cot_hist", json.dumps({"ts": time.time(), "error": f"{type(e).__name__}: {str(e)[:120]}"}))
            logging.getLogger("tst.labs").warning("cot history: %s", e)
        await asyncio.sleep(86400)


def lab_cot(db: DB, sym: str = "XAU") -> dict:
    from . import judge
    dates, closes = daily(db, sym)
    src = "cot_hist" if _rows(db, "SELECT 1 FROM cot_hist WHERE symbol=? LIMIT 1", (sym,)) else "cot"
    rows = [(r["d"], r["mm_long"] - r["mm_short"]) for r in _rows(
        db, f"SELECT d, mm_long, mm_short FROM {src} WHERE symbol=? AND mm_long IS NOT NULL AND mm_short IS NOT NULL "
            "ORDER BY d", (sym,))]
    trades, busy_until = [], ""
    for i in range(156, len(rows)):
        d, net = rows[i]
        past = [x for _, x in rows[i - 156:i]]
        rank = (sum(1 for x in past if x < net) + 0.5 * sum(1 for x in past if x == net)) / len(past)   # midrank
        if 0.1 < rank < 0.9:
            continue
        start = (datetime.fromisoformat(d) + timedelta(days=6)).strftime("%Y-%m-%d")
        if start <= busy_until:
            continue
        h = _hold(dates, closes, start, 20)
        if not h:
            continue
        k = bisect_left(dates, start)
        busy_until = dates[k + 20]
        trades.append((h[0], h[1] * (-1 if rank >= 0.9 else 1)))
    return verdict(trades, judge.full_cost(sym, "1mo"), 15)


LABS = [
    {"id": "L1", "name": "Fed sürprizi", "fn": lab_fed,
     "question": "Fed qərar günü 2 illik faiz 5 bazis bəndindən çox qalxanda (gözləniləndən sərt) qızıl sonrakı 5 gündə "
                 "düşürmü; enəndə qalxırmı?",
     "data": "Fed qərarları (hadisə kitabxanası), 2 illik ABŞ faizi (FRED), qızılın gündəlik bağlanışı"},
    {"id": "L2", "name": "ABŞ rəqəmləri sürprizi", "fn": lab_data,
     "question": "CPI və iş yerləri gözləntidən güclü gələndə qızıl sonrakı 4 gündə də düşməyə davam edirmi; zəif "
                 "gələndə qalxırmı?",
     "data": "CPI və NFP buraxılışları, ilk dərc olunmuş rəqəm və gözlənti (hadisə kitabxanası)"},
    {"id": "L3", "name": "İri fondlar həddə (COT)", "fn": lab_cot,
     "question": "İri fondların qızılda xalis alışı son 3 ilin ən yüksək 10 %-nə çatanda qızıl sonrakı 20 gündə "
                 "düşürmü; ən aşağı 10 %-də qalxırmı?",
     "data": "CFTC COT həftəlik hesabatı (2006-cı ildən, laboratoriyanın öz cədvəli), qızılın gündəlik bağlanışı"},
]


def _other_tests(db: DB) -> list[dict]:
    """The tests that already run elsewhere, in the same words (one place to see every lab)."""
    out = []
    try:
        st = json.loads(db.get("eventlib:state") or "null") or {}
        c = ((st.get("test") or {}).get("cells") or {}).get("XAU:1w") or {}
        if c:
            out.append({"id": "E", "name": "Hadisə analoqları", "question": "Keçmişdəki eyni növ hadisələrdən sonrakı "
                        "hərəkət bu dəfəni göstərirmi? (1 həftə, qızıl)", "status": "sübut" if c.get("passed") else "yox",
                        "n": c.get("n"), "hit_rate": c.get("hit"), "net_avg_pct": c.get("net_avg_pct")})
    except ValueError:
        pass
    for key, name, q, path in (
            ("dbhist:result", "Böyük oyunçu (tək iri əməliyyat)", "Tək iri alış/satış qızılın sonrakı 15 dəqiqəsini "
             "göstərirmi? (12 ay)", ("m15",)),
            ("dbstats:result", "CME açıq mövqelər", "Qiymət və açıq mövqe birlikdə qızılın ertəsi gününü göstərirmi? "
             "(5 il)", ("gold_1d",))):
        try:
            r = json.loads(db.get(key) or "null") or {}
        except ValueError:
            r = {}
        if not r:
            continue
        cell = r
        for p in path:
            cell = cell.get(p) or {}
        out.append({"id": "D" if key.startswith("dbhist") else "C", "name": name, "question": q,
                    "status": r.get("status") or cell.get("status"), "n": cell.get("n"),
                    "hit_rate": cell.get("hit_rate"), "net_avg_pct": cell.get("net_avg_pct")})
    return out


def build(db: DB) -> dict:
    out = {"ts": time.time(), "labs": [], "others": _other_tests(db)}
    for lab in LABS:
        row = {k: v for k, v in lab.items() if k != "fn"}
        try:
            row["gold"] = lab["fn"](db, "XAU")
            row["silver_shown"] = lab["fn"](db, "XAG")
        except Exception as e:           # one lab's failure is shown, it never hides the others
            row["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        out["labs"].append(row)
    db.put("labs:last", json.dumps(out, ensure_ascii=False))
    return out
