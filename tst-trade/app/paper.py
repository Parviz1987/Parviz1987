"""Kağız ticarət (owner 2026-11-25, from the Radar Gold design: risk engine, simulator, order journal, emergency stop).

NO real money and no broker: a virtual account in our own database. It acts ONLY on an AL / SAT that the decision
already gives — which needs the Judge's proof, the one-look final test, the independent re-check, the owner's approval
in the registry and an open risk gate. Until something is approved, it waits and does nothing.

- Risk engine (each proposal): stale price (older than 2 minutes), the same desk already open, daily loss limit,
  total open risk limit, emergency stop -> rejected with the reason. Size = risk budget / (stop distance + cost buffer),
  rounded down to 0.01 oz.
- Simulator: entry at the live price plus half the spread and slippage (judge costs); stop at the opposite edge of
  the forecast's 80 % range, target the same distance the other way; checked against each closed minute (high/low):
  when one minute touches both, the stop counts; a gap past the stop fills at the worse price; the horizon's end
  closes the position at the market. The overnight fee is charged for the nights held.
- Journal: every proposal (accepted or rejected with why), every fill, every close — the account is always rebuilt
  from the journal, so a restart loses nothing. Emergency stop: no new risk; open positions follow their exits."""
from __future__ import annotations

import json
import math
import time

from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, symbol TEXT, horizon TEXT,
  method TEXT, dir INTEGER, oz REAL, entry REAL, stop REAL, target REAL, expires REAL, status TEXT, reason TEXT,
  exit REAL, exit_ts REAL, pnl REAL, cost REAL);
"""
DEFAULTS = {"start_usd": 10000.0, "risk_pct": 0.5, "daily_loss_pct": 2.0, "open_risk_pct": 2.0, "max_drawdown_pct": 10.0}
# owner's policy 2026-11-26: one method at most 25 % of the account (and never above half Kelly of its record), 2 % a
# day, everything stops at a 10 % fall from the peak (it restarts only when the owner releases the stop)


def ensure(db: DB) -> None:
    db.script(SCHEMA)


def settings(db: DB) -> dict:
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(db.get("paper:settings") or "{}"))
    except ValueError:
        pass
    s["stopped"] = db.get("paper:stop") == "1"
    return s


def set_settings(db: DB, values: dict) -> dict:
    s = settings(db)
    for k in DEFAULTS:
        if k in values:
            v = float(values[k])
            if not (0 < v <= (1e9 if k == "start_usd" else 20)):
                raise ValueError(f"{k}: düzgün deyil")
            s[k] = v
    db.put("paper:settings", json.dumps({k: s[k] for k in DEFAULTS}))
    return settings(db)


def emergency(db: DB, on: bool) -> dict:
    db.put("paper:stop", "1" if on else "0")
    if not on:                       # released by the owner: the 10 % fall is measured afresh from here
        db.put("paper:peak_reset_ts", str(time.time()))
    return settings(db)


def _equity(db: DB, s: dict) -> float:
    r = db.execute("SELECT COALESCE(SUM(pnl), 0) p FROM paper_orders WHERE status='bağlandı'").fetchone()
    return s["start_usd"] + r["p"]


def _day_pnl(db: DB, now: float) -> float:
    day0 = now - now % 86400
    return db.execute("SELECT COALESCE(SUM(pnl), 0) p FROM paper_orders WHERE status='bağlandı' AND exit_ts >= ?",
                      (day0,)).fetchone()["p"]


def _peak_drawdown(db: DB, s: dict, open_loss: float = 0.0) -> float:
    """The fall from the equity peak, counted since the owner last released the stop (closed results; open losses
    added at the end)."""
    since = float(db.get("paper:peak_reset_ts") or 0)
    eq0 = s["start_usd"] + db.execute("SELECT COALESCE(SUM(pnl), 0) p FROM paper_orders WHERE status='bağlandı' AND "
                                      "exit_ts <= ?", (since,)).fetchone()["p"]
    eq = peak = eq0
    for r in db.execute("SELECT pnl FROM paper_orders WHERE status='bağlandı' AND exit_ts > ? ORDER BY exit_ts",
                        (since,)).fetchall():
        eq += r["pnl"] or 0
        peak = max(peak, eq)
    eq -= max(0.0, open_loss)
    return (peak - eq) / peak if peak > 0 else 0.0


def propose(db: DB, sym: str, horizon: str, method: str, p_up: float, price: float | None, price_age: float,
            lo80: float, hi80: float, expires: float, now: float, size: float = 1.0, cap: float | None = None,
            method_id: str | None = None) -> dict:
    """The risk engine: accept (filled at once in the simulator) or reject with the reason. Every proposal is kept."""
    from .judge import COST, SLIP
    ensure(db)
    s = settings(db)
    d = 1 if p_up > 0.5 else -1
    why = None
    if s["stopped"]:
        why = "təcili dayanma açıqdır"
    elif price is None or price_age > 120:
        why = "qiymət köhnədir"
    elif db.execute("SELECT 1 FROM paper_orders WHERE symbol=? AND horizon=? AND status='açıq'", (sym, horizon)).fetchone():
        why = "bu masada artıq açıq mövqe var"
    eq = _equity(db, s)
    if not why and -_day_pnl(db, now) >= eq * s["daily_loss_pct"] / 100:
        why = "günlük zərər limiti doldu"
    if not why and _peak_drawdown(db, s) * 100 >= s.get("max_drawdown_pct", 10.0):
        emergency(db, True)
        why = f"zirvədən {s.get('max_drawdown_pct', 10.0):.0f} % düşüb: hər şey avtomatik dayandı"
    if not why and size <= 0:
        why = "Avtomatik Hakimin payı 0-dır"
    stop = lo80 if d > 0 else hi80
    dist = abs(price - stop) if price else 0
    if not why and (dist <= 0 or dist / price > 0.2):
        why = "stop məsafəsi düzgün deyil"
    cost_oz = price * COST.get(sym, 0) * (1 + SLIP) if price else 0
    oz = 0.0
    if not why:
        budget = eq * s["risk_pct"] / 100 * min(1.0, size)      # the automatic Judge's share (small step = quarter)
        oz = math.floor(budget / (dist + cost_oz) * 100) / 100
        mid = method_id or method
        held = db.execute("SELECT COALESCE(SUM(entry * oz), 0) v FROM paper_orders WHERE status='açıq' AND method=?",
                          (mid,)).fetchone()["v"]
        room = max(0.0, cap * eq - held) if cap is not None else None   # one method: half Kelly, ≤ 25 % of the account
        if price and room is not None and oz * price > room:
            oz = math.floor(room / price * 100) / 100
        open_risk = db.execute("SELECT COALESCE(SUM(ABS(entry - stop) * oz), 0) r FROM paper_orders WHERE status='açıq'"
                               ).fetchone()["r"]
        if oz <= 0:
            why = "ölçü 0-dır (risk büdcəsi kiçikdir)"
        elif open_risk + oz * dist > eq * s["open_risk_pct"] / 100:
            why = "ümumi açıq risk limiti doldu"
    if why:
        db.execute("INSERT INTO paper_orders(ts, symbol, horizon, method, dir, oz, entry, stop, target, expires, status, "
                   "reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (now, sym, horizon, method, d, 0, price, None, None, expires,
                                                              "rədd", why))
        return {"status": "rədd", "reason": why}
    entry = price + d * cost_oz / 2                        # half the spread and slippage on the way in
    target = entry + d * dist
    db.execute("INSERT INTO paper_orders(ts, symbol, horizon, method, dir, oz, entry, stop, target, expires, status, reason, "
               "cost) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (now, sym, horizon, method, d, oz, entry, stop, target, expires,
                                                           "açıq", "qəbul: risk mühərriki", cost_oz * oz))
    return {"status": "açıq", "oz": oz, "entry": entry, "stop": stop, "target": target}


def manage(db: DB, now: float) -> int:
    """Exits from the closed one-minute candles since entry: stop first when a minute touches both, a gap past the
    stop at the worse open, the horizon's end at the last close; half the spread on the way out, the nights' fee."""
    from .judge import COST, SLIP, SWAP, SWAP_GUESS
    ensure(db)
    closed = 0
    for o in db.execute("SELECT * FROM paper_orders WHERE status='açıq'").fetchall():
        bars = db.execute("SELECT t, o, h, l, c FROM candles WHERE symbol=? AND tf='1m' AND t>=? AND t+60<=? ORDER BY t",
                          (o["symbol"], o["ts"] - o["ts"] % 60 + 60, now)).fetchall()
        exit_p = exit_t = None
        why = ""
        for b in bars:
            d = o["dir"]
            if (d > 0 and b["o"] <= o["stop"]) or (d < 0 and b["o"] >= o["stop"]):
                exit_p, exit_t, why = b["o"], b["t"], "stop (boşluqla)"
            elif (d > 0 and b["l"] <= o["stop"]) or (d < 0 and b["h"] >= o["stop"]):
                exit_p, exit_t, why = o["stop"], b["t"] + 60, "stop"
            elif (d > 0 and b["h"] >= o["target"]) or (d < 0 and b["l"] <= o["target"]):
                exit_p, exit_t, why = o["target"], b["t"] + 60, "hədəf"
            elif b["t"] + 60 >= o["expires"]:
                exit_p, exit_t, why = b["c"], b["t"] + 60, "üfüq bitdi"
            if exit_p is not None:
                break
        if exit_p is None:
            continue
        half = exit_p * COST.get(o["symbol"], 0) * (1 + SLIP) / 2
        exit_p -= o["dir"] * half
        nights = int(exit_t // 86400 - o["ts"] // 86400)
        fee = nights * SWAP.get(o["symbol"], SWAP_GUESS) * exit_p * o["oz"]
        pnl = (exit_p - o["entry"]) * o["dir"] * o["oz"] - fee
        db.execute("UPDATE paper_orders SET status='bağlandı', exit=?, exit_ts=?, pnl=?, reason=reason || ' → ' || ? "
                   "WHERE id=?", (exit_p, exit_t, pnl, why, o["id"]))
        closed += 1
    return closed


def step(db: DB, engine, decisions: dict, now: float) -> None:
    """Called every minute after the decisions: new proposals for every AL / SAT, then the exits."""
    from .candles import METALS
    ensure(db)
    for sym in METALS:
        for d in (decisions.get(sym) or {}).get("desks", []):
            if d.get("call") not in ("AL", "SAT"):
                continue
            h = d["horizon"]
            f = db.execute("SELECT method, lo80, hi80, target_t FROM forecasts WHERE symbol=? AND horizon=? AND "
                           "mode='live' AND method='rw' AND target_t > ? ORDER BY issued_t DESC LIMIT 1",
                           (sym, h, now)).fetchone()
            if not f or db.execute("SELECT 1 FROM paper_orders WHERE symbol=? AND horizon=? AND ts > ?",
                                   (sym, h, now - 3600)).fetchone():
                continue
            q = (engine.quotes or {}).get(sym) or {}
            propose(db, sym, h, str(d.get("method_id") or d.get("method")), d["p_up"], q.get("price"),
                    now - (q.get("recv_ts") or 0), f["lo80"], f["hi80"], f["target_t"], now,
                    size=float(d.get("size", 1.0)), cap=float(d.get("cap", 0.25)))
    manage(db, now)


def view(db: DB) -> dict:
    ensure(db)
    s = settings(db)
    rows = [dict(r) for r in db.execute("SELECT * FROM paper_orders ORDER BY id DESC LIMIT 100").fetchall()]
    done = [r for r in rows if r["status"] == "bağlandı"]
    wins = [r for r in done if r["pnl"] > 0]
    eq_curve, eq, peak, mdd = [], s["start_usd"], s["start_usd"], 0.0
    for r in sorted(done, key=lambda r: r["exit_ts"]):
        eq += r["pnl"]
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak if peak else 0)
        eq_curve.append([r["exit_ts"], round(eq, 2)])
    gross_w = sum(r["pnl"] for r in wins)
    gross_l = -sum(r["pnl"] for r in done if r["pnl"] <= 0)
    return {"settings": s, "equity": round(_equity(db, s), 2), "orders": rows,
            "open": [r for r in rows if r["status"] == "açıq"],
            "stats": {"trades": len(done), "win_rate": len(wins) / len(done) if done else None,
                      "profit_factor": gross_w / gross_l if gross_l else None, "max_drawdown": round(mdd, 4),
                      "expectancy": sum(r["pnl"] for r in done) / len(done) if done else None},
            "equity_curve": eq_curve}
