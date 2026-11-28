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
Silver is shown for each lab, it does not decide.
Results 28.11 04:05–04:54 NY: L1 «yox» (26, 50 %), L2 «az» (92 < 100, 44.6 %), L3 «yox» (26, 38.5 %).

PRE-REGISTERED 28.11.2026 04:55 NY, before any of these three results was computed (same bar, same verdict words):

L4  Dollar ilə birgə — gold and the dollar index usually move opposite. A day when BOTH rise (gold ≥ +0.5 %, DXY
    ≥ +0.3 %: buying that ignores the dollar — safe-haven or central-bank demand) → gold up; when both fall (gold
    ≤ −0.5 %, DXY ≤ −0.3 %) → gold down. Trade: from the next day's close, 5 trading days; no new trade while one
    runs; cost judge.full_cost("XAU", "1w"). Proof: ≥ 30 trades.
L5  Neft şoku — WTI crude moves ≥ 5 % in a day: up → gold up (inflation fear), down → gold down. Trade: from the next
    day's close, 5 trading days; no overlap; cost judge.full_cost("XAU", "1w"). Proof: ≥ 20 trades.
L6  Müharibə xəbəri sıçrayışı — the event library's GEO days (GDELT: the share of world news about war and strikes
    jumps far above its own 90 days; known only at that day's end): gold up (safe haven). Trade: from the close of the
    first trading day on or after the event's time, 5 trading days; no overlap; cost judge.full_cost("XAU", "1w").
    Proof: ≥ 20 trades.
Results 28.11 04:59 NY: L4 «yox» (52, 53.8 %), L5 «yox» (45, 55.6 %), L6 «yox» (21, 52.4 %).

PRE-REGISTERED 28.11.2026 14:51 NY — the corridor labs (owner 28.11: «koridoru tapaq, alqı-satqını koridora əsasən
edək»), before any of these results was computed. The corridor is the system's own range forecast (method «vahid»,
else «up»: in history both carry the same range), already calibrated on average (1d 80 % range held 80.6 % of 1 959
days). The question is not coverage but money: does trading AT the corridor's edges pay after cost?
K1  Daily, 80 % edge, back toward the middle: the 1-day forecast's own day (the daily candle the forecast was made
    for). Low ≤ lo80 and high < hi80 → bought at lo80; high ≥ hi80 and low > lo80 → sold at hi80; both edges the same
    day → no trade (their order is unknown); exit at that day's close. Cost judge.full_cost("XAU", "4h") (no night).
K2  The same at the 50 % edge.
K3  Weekly, 80 % edge: the 1-week forecast's week of daily candles; the first day that touches an edge opens the
    trade at that edge (a day touching both → no trade that week); exit at the week's last close; cost
    judge.full_cost("XAU", "1w").
K4  The same at the 50 % edge.
Proof for K1–K4: ≥ 100 trades, the bar above. Shown, not deciding: the corridor's width, coverage, the interval
(Winkler) score and whether misses come in clusters, per horizon.
Results 28.11 14:56 NY: K1 «yox» (717, 47.3 %), K2 «yox» (1 460, 43.2 %), K3 «yox» (154, 50.6 %), K4 «yox» (342, 49.7 %).
FLAW found in my own K rule (28.11 15:00, before reading anything into it): «both edges the same day → no trade» uses the
whole day's range, known only at its end — the days kept are biased toward one-way days, which makes turning back look
worse and breaking out look better than they are. K1–K4 stay shown as registered, with this note; they decide nothing.

PRE-REGISTERED 28.11.2026 14:58 NY — corrected corridor labs on HOURLY candles (about eleven months on the server):
the first hour that reaches an edge decides; the trade opens at that edge and closes at the forecast's end (the day's
or the week's last hourly close), whatever happens after; an hour reaching both edges → that forecast has no trade
(rare: within one hour). Each corridor is tested both ways, as separate labs:
KR1/KB1 daily 80 % edge, KR2/KB2 daily 50 %, KR3/KB3 weekly 80 %, KR4/KB4 weekly 50 %. R = turn back toward the middle
(buy the lower edge, sell the upper); B = break out (buy the upper edge, sell the lower). Cost: daily
judge.full_cost("XAU", "4h"), weekly judge.full_cost("XAU", "1w"). Proof: ≥ 60 trades (eleven months), p < 0.01,
average after cost > 0, both halves positive."""
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


def _pairs(db: DB, sym: str, other: str) -> tuple[list[str], list[float], dict[str, float]]:
    dates, closes = daily(db, sym)
    od, oc = daily(db, other)
    return dates, closes, dict(zip(od, oc))


def _day_signals(dates, closes, sig) -> list[tuple[str, float]]:
    """sig(i) → +1 / −1 / 0 for day i; trade from the close of day i+1 for 5 trading days, no overlap."""
    trades, busy = [], -1
    for i in range(1, len(dates) - 6):
        if i + 1 <= busy:
            continue
        way = sig(i)
        if not way:
            continue
        trades.append((dates[i + 1], (closes[i + 6] / closes[i + 1] - 1) * way))
        busy = i + 6
    return trades


def lab_dollar(db: DB, sym: str = "XAU") -> dict:
    from . import judge
    dates, closes, dx = _pairs(db, sym, "DXY")

    def sig(i):
        a, b = dates[i - 1], dates[i]
        if a not in dx or b not in dx:
            return 0
        g, u = closes[i] / closes[i - 1] - 1, dx[b] / dx[a] - 1
        return 1 if g >= 0.005 and u >= 0.003 else -1 if g <= -0.005 and u <= -0.003 else 0
    return verdict(_day_signals(dates, closes, sig), judge.full_cost(sym, "1w"), 30)


def lab_oil(db: DB, sym: str = "XAU") -> dict:
    from . import judge
    dates, closes, oil = _pairs(db, sym, "OIL")

    def sig(i):
        a, b = dates[i - 1], dates[i]
        if a not in oil or b not in oil or not oil[a]:
            return 0
        ch = oil[b] / oil[a] - 1
        return 1 if ch >= 0.05 else -1 if ch <= -0.05 else 0
    return verdict(_day_signals(dates, closes, sig), judge.full_cost(sym, "1w"), 20)


def lab_geo(db: DB, sym: str = "XAU") -> dict:
    from . import judge
    dates, closes = daily(db, sym)
    trades, busy = [], ""
    for r in _rows(db, "SELECT t FROM ev_lib WHERE kind='GEO' ORDER BY t"):
        d = datetime.fromtimestamp(r["t"], timezone.utc).strftime("%Y-%m-%d")
        if d <= busy:
            continue
        h = _hold(dates, closes, d, 5)
        if not h:
            continue
        busy = dates[bisect_left(dates, h[0]) + 5]
        trades.append(h)
    return verdict(trades, judge.full_cost(sym, "1w"), 20)


def _corridor_rows(db: DB, sym: str, horizon: str) -> list:
    rows = _rows(db, "SELECT issued_t, target_t, price0, price1, lo50, hi50, lo80, hi80, method FROM forecasts "
                     "WHERE symbol=? AND horizon=? AND method IN ('vahid', 'up') AND price1 IS NOT NULL "
                     "ORDER BY issued_t, method DESC", (sym, horizon))
    seen, out = set(), []
    for r in rows:                              # one row per forecast moment: «vahid» first, else «up»
        if r["issued_t"] in seen:
            continue
        seen.add(r["issued_t"])
        out.append(r)
    return out


def _path(db: DB, sym: str, a: int, b: int) -> list:
    return _rows(db, "SELECT t, h, l, c FROM candles WHERE symbol=? AND tf='1d' AND t >= ? AND t < ? ORDER BY t",
                 (sym, a, b))


def lab_corridor(db: DB, sym: str = "XAU", horizon: str = "1d", band: str = "80") -> dict:
    from . import judge
    lo_k, hi_k = f"lo{band}", f"hi{band}"
    trades = []
    for r in _corridor_rows(db, sym, horizon):
        days = _path(db, sym, r["issued_t"], r["target_t"])
        if not days:
            continue
        lo, hi, entry = r[lo_k], r[hi_k], None
        for d in days:
            down, up = d["l"] <= lo, d["h"] >= hi
            if down and up:
                break                            # both edges in one day: order unknown, no trade
            if down or up:
                entry = (1, lo) if down else (-1, hi)
                break
        if not entry:
            continue
        way, px = entry
        close = days[-1]["c"]
        ret = (close / px - 1) if way > 0 else (px / close - 1)
        trades.append((datetime.fromtimestamp(r["issued_t"], timezone.utc).strftime("%Y-%m-%d"), ret))
    return verdict(trades, judge.full_cost(sym, "4h" if horizon == "1d" else "1w"), 100)


def lab_corridor_h(db: DB, sym: str = "XAU", horizon: str = "1d", band: str = "80", way_kind: str = "R") -> dict:
    """The corrected corridor rule on hourly candles: the first hour reaching an edge opens the trade at that edge."""
    from . import judge
    lo_k, hi_k = f"lo{band}", f"hi{band}"
    shift = 7200                     # a daily candle labelled D runs from 22:00 UTC the evening before (candles.bucket)
    trades = []
    for r in _corridor_rows(db, sym, horizon):
        a, b = r["issued_t"] - shift, r["target_t"] - shift
        hours = _rows(db, "SELECT t, h, l, c FROM candles WHERE symbol=? AND tf='1h' AND t >= ? AND t < ? ORDER BY t",
                      (sym, a, b))
        if len(hours) < (12 if horizon == "1d" else 60):
            continue                 # no hourly path for this forecast (before the hourly history)
        lo, hi, entry = r[lo_k], r[hi_k], None
        for x in hours:
            down, up = x["l"] <= lo, x["h"] >= hi
            if down and up:
                break
            if down or up:
                edge_dir = 1 if down else -1          # turning back: buy the lower edge, sell the upper
                entry = (edge_dir if way_kind == "R" else -edge_dir, lo if down else hi)
                break
        if not entry:
            continue
        way, px = entry
        close = hours[-1]["c"]
        trades.append((datetime.fromtimestamp(r["issued_t"], timezone.utc).strftime("%Y-%m-%d"),
                       (close / px - 1) * way))
    return verdict(trades, judge.full_cost(sym, "4h" if horizon == "1d" else "1w"), 60)


def corridor_quality(db: DB, sym: str = "XAU") -> dict:
    """Per horizon: coverage of the 50/80 % corridor, its mean width (% of price), the Winkler score of the 80 % one
    (width plus a penalty for every miss; lower is better) and whether misses cluster (P(miss | miss before) / P(miss))."""
    out = {}
    for h in ("1d", "3d", "1w", "10d", "1mo"):
        rows = _corridor_rows(db, sym, h)
        if len(rows) < 30:
            continue
        n = len(rows)
        miss = [not (r["lo80"] <= r["price1"] <= r["hi80"]) for r in rows]
        c50 = sum(1 for r in rows if r["lo50"] <= r["price1"] <= r["hi50"]) / n
        width = sum((r["hi80"] - r["lo80"]) / r["price0"] for r in rows) / n
        wink = sum(((r["hi80"] - r["lo80"]) + (2 / 0.2) * max(0, r["lo80"] - r["price1"], r["price1"] - r["hi80"]))
                   / r["price0"] for r in rows) / n
        pm = sum(miss) / n
        after = [miss[i] for i in range(1, n) if miss[i - 1]]
        out[h] = {"n": n, "cover50": round(c50, 3), "cover80": round(1 - pm, 3), "width80_pct": round(width * 100, 2),
                  "winkler80_pct": round(wink * 100, 2),
                  "miss_cluster": round((sum(after) / len(after)) / pm, 2) if after and pm else None}
    return out


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
    {"id": "L4", "name": "Dollar ilə birgə", "fn": lab_dollar,
     "question": "Qızıl və dollar eyni gündə birlikdə qalxanda (adi halda tərs gedirlər) qızıl sonrakı 5 gündə də "
                 "qalxırmı; birlikdə düşəndə düşürmü?",
     "data": "Qızılın və dollar indeksinin gündəlik bağlanışı"},
    {"id": "L5", "name": "Neft şoku", "fn": lab_oil,
     "question": "Neft bir gündə 5 %-dən çox qalxanda qızıl sonrakı 5 gündə qalxırmı; kəskin düşəndə düşürmü?",
     "data": "WTI neftinin və qızılın gündəlik bağlanışı"},
    {"id": "L6", "name": "Müharibə xəbəri sıçrayışı", "fn": lab_geo,
     "question": "Dünya xəbərlərində müharibə və zərbə mövzusu kəskin artandan sonra qızıl 5 gündə qalxırmı?",
     "data": "GDELT (hadisə kitabxanasının geosiyasi günləri), qızılın gündəlik bağlanışı"},
    {"id": "K1", "name": "Günlük koridor, 80 % kənar", "fn": lambda db, s: lab_corridor(db, s, "1d", "80"),
     "question": "Gün ərzində qiymət sistemin 80 %-lik günlük koridorunun aşağı kənarına düşəndə alıb (yuxarı kənarına "
                 "çıxanda satıb) günün sonunda bağlamaq xərcdən sonra qazandırırmı?",
     "data": "Sistemin günlük koridor proqnozları (8 il keçmiş sınaq), qızılın gündəlik ən aşağı / ən yüksək / bağlanışı"},
    {"id": "K2", "name": "Günlük koridor, 50 % kənar", "fn": lambda db, s: lab_corridor(db, s, "1d", "50"),
     "question": "Eyni qayda 50 %-lik (daha dar) koridorun kənarlarında qazandırırmı?",
     "data": "Sistemin günlük koridor proqnozları, qızılın gündəlik şamları"},
    {"id": "K3", "name": "Həftəlik koridor, 80 % kənar", "fn": lambda db, s: lab_corridor(db, s, "1w", "80"),
     "question": "Həftə ərzində qiymət 80 %-lik həftəlik koridorun kənarına ilk dəfə toxunanda tərsinə girib həftənin "
                 "sonunda bağlamaq qazandırırmı?",
     "data": "Sistemin həftəlik koridor proqnozları, qızılın gündəlik şamları"},
    {"id": "K4", "name": "Həftəlik koridor, 50 % kənar", "fn": lambda db, s: lab_corridor(db, s, "1w", "50"),
     "question": "Eyni qayda 50 %-lik həftəlik koridorun kənarlarında qazandırırmı?",
     "data": "Sistemin həftəlik koridor proqnozları, qızılın gündəlik şamları"},
    {"id": "KR1", "name": "Günlük koridor 80 % — geri dönüş (saatlıq)",
     "fn": lambda db, s: lab_corridor_h(db, s, "1d", "80", "R"),
     "question": "Günlük 80 %-lik koridorda kənara toxunanda tərsinə (aşağı kənarda al, yuxarıda sat) girib müddətin sonunda bağlamaq xərcdən sonra qazandırırmı?",
     "data": "Sistemin koridor proqnozları, qızılın saatlıq şamları (~11 ay)"},
    {"id": "KB1", "name": "Günlük koridor 80 % — qırılma (saatlıq)",
     "fn": lambda db, s: lab_corridor_h(db, s, "1d", "80", "B"),
     "question": "Günlük 80 %-lik koridorda kənardan çıxanda o tərəfə (yuxarı kənarda al, aşağıda sat) girib müddətin sonunda bağlamaq xərcdən sonra qazandırırmı?",
     "data": "Sistemin koridor proqnozları, qızılın saatlıq şamları (~11 ay)"},
    {"id": "KR2", "name": "Günlük koridor 50 % — geri dönüş (saatlıq)",
     "fn": lambda db, s: lab_corridor_h(db, s, "1d", "50", "R"),
     "question": "Günlük 50 %-lik koridorda kənara toxunanda tərsinə (aşağı kənarda al, yuxarıda sat) girib müddətin sonunda bağlamaq xərcdən sonra qazandırırmı?",
     "data": "Sistemin koridor proqnozları, qızılın saatlıq şamları (~11 ay)"},
    {"id": "KB2", "name": "Günlük koridor 50 % — qırılma (saatlıq)",
     "fn": lambda db, s: lab_corridor_h(db, s, "1d", "50", "B"),
     "question": "Günlük 50 %-lik koridorda kənardan çıxanda o tərəfə (yuxarı kənarda al, aşağıda sat) girib müddətin sonunda bağlamaq xərcdən sonra qazandırırmı?",
     "data": "Sistemin koridor proqnozları, qızılın saatlıq şamları (~11 ay)"},
    {"id": "KR3", "name": "Həftəlik koridor 80 % — geri dönüş (saatlıq)",
     "fn": lambda db, s: lab_corridor_h(db, s, "1w", "80", "R"),
     "question": "Həftəlik 80 %-lik koridorda kənara toxunanda tərsinə (aşağı kənarda al, yuxarıda sat) girib müddətin sonunda bağlamaq xərcdən sonra qazandırırmı?",
     "data": "Sistemin koridor proqnozları, qızılın saatlıq şamları (~11 ay)"},
    {"id": "KB3", "name": "Həftəlik koridor 80 % — qırılma (saatlıq)",
     "fn": lambda db, s: lab_corridor_h(db, s, "1w", "80", "B"),
     "question": "Həftəlik 80 %-lik koridorda kənardan çıxanda o tərəfə (yuxarı kənarda al, aşağıda sat) girib müddətin sonunda bağlamaq xərcdən sonra qazandırırmı?",
     "data": "Sistemin koridor proqnozları, qızılın saatlıq şamları (~11 ay)"},
    {"id": "KR4", "name": "Həftəlik koridor 50 % — geri dönüş (saatlıq)",
     "fn": lambda db, s: lab_corridor_h(db, s, "1w", "50", "R"),
     "question": "Həftəlik 50 %-lik koridorda kənara toxunanda tərsinə (aşağı kənarda al, yuxarıda sat) girib müddətin sonunda bağlamaq xərcdən sonra qazandırırmı?",
     "data": "Sistemin koridor proqnozları, qızılın saatlıq şamları (~11 ay)"},
    {"id": "KB4", "name": "Həftəlik koridor 50 % — qırılma (saatlıq)",
     "fn": lambda db, s: lab_corridor_h(db, s, "1w", "50", "B"),
     "question": "Həftəlik 50 %-lik koridorda kənardan çıxanda o tərəfə (yuxarı kənarda al, aşağıda sat) girib müddətin sonunda bağlamaq xərcdən sonra qazandırırmı?",
     "data": "Sistemin koridor proqnozları, qızılın saatlıq şamları (~11 ay)"},
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
    out = {"ts": time.time(), "labs": [], "others": _other_tests(db), "corridor_quality": corridor_quality(db)}
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
