"""Risk qapısı (risk gate) and Qərar (decision): plain rules, no brain can change them.

Risk gate, per metal — closed (no direction is shown as actionable) when any of:
- the price is not LIVE (stale or offline feed);
- a high-impact US release is within 60 minutes ahead or 30 minutes behind;
- the market is thin (liquidity agent: wide spread or very quiet);
- the market is wild: the last hour's 15-minute moves are more than twice their usual size.

Decision, per metal and horizon — «AL» (buy) or «SAT» (sell) only when ALL hold; otherwise «GÖZLƏ» (wait) with the reason:
- the Judge has proven a method on this desk (status «sübut»: beats the bar, not chance, pays after the spread);
- that method's latest live forecast has a direction;
- the risk gate is open.
It is an indication on the panel only: nothing here places an order (trading needs the owner's separate decision)."""
from __future__ import annotations

import time

from . import candles, forecast, judge
from .db import DB


def gate(db: DB, engine, symbol: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    reasons = []
    status = engine.status(symbol, now) if engine is not None else "OFFLINE"
    reflex = engine.reflex.closed(symbol, now) if engine is not None and hasattr(engine, "reflex") else None
    if reflex:
        reasons.append(reflex)
    if status not in ("LIVE", "DEMO"):
        reasons.append(f"qiymət canlı deyil ({status})")
    try:
        from .engine import EventLookup
        if EventLookup(db).near(now):
            reasons.append(EVENT_REASON)
    except Exception:
        pass
    liq = engine.liquidity.view(symbol, now) if engine is not None and hasattr(engine, "liquidity") else None
    if liq and liq["state"] == "nazik":
        reasons += liq["reasons"]
    rows = candles.closed(db, symbol, "15m", now, limit=200)
    rets = [abs(b["c"] / a["c"] - 1) for a, b in zip(rows, rows[1:]) if a["c"]]
    if len(rets) > 50:
        moved = sorted(r for r in rets[:-4] if r > 0)
        usual = moved[len(moved) // 2] if moved else 0
        last = sum(rets[-4:]) / 4
        if usual and last > 2 * usual:
            reasons.append(f"bazar dalğalıdır: son saatın hərəkəti adətdən {last / usual:.1f} dəfə böyükdür")
    return {"symbol": symbol, "open": not reasons, "reasons": reasons, "liquidity": liq}


EVENT_REASON = "mühüm ABŞ rəqəminə 60 dəqiqədən az qalıb və ya 30 dəqiqədən az keçib"
EVENT_METHODS = ("surprise", "bazarlar", "xeber")      # built for the release window: it must not silence them


def decision(db: DB, engine, symbol: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    g = gate(db, engine, symbol, now)
    desks = []
    for h in forecast.HORIZONS:
        verdict = judge.verdict(db, symbol, h, now)          # the one verdict shared with the card and outlook
        row = {"horizon": h, "name": forecast.HORIZON_NAMES[h], "call": "GÖZLƏ", "method": None, "p_up": None}
        be = judge.breakeven(db, symbol, h)
        row["breakeven"] = be
        if be is not None and be > judge.BREAKEVEN_MAX:
            row["why"] = (f"bu masada xərc çox böyükdür: sadəcə xərci ödəmək üçün {round(be * 100)} % düz çıxmaq "
                          "lazımdır (Capital spredi); proqnoz göstərici kimi qalır")
        elif verdict["status"] != "sübut":
            # the owner's policy (2026-11-26): a method the automatic Judge scores >= 70 trades on paper with a small
            # share before it is fully proven; the score decides, not a person
            from . import autojudge
            b = autojudge.best(db, symbol, h)
            f = None
            if b:
                f = db.execute("SELECT p_up FROM forecasts WHERE symbol=? AND horizon=? AND method=? AND mode='live' AND "
                               "target_t > ? ORDER BY issued_t DESC LIMIT 1", (symbol, h, b[0], now)).fetchone()
            if not b:
                row["why"] = "Hakimin sübutu yoxdur və heç bir üsulun balı 70-ə çatmır: istiqamət göstərilmir"
            elif not f or f["p_up"] == 0.5:
                row["why"] = f"{forecast.METHOD_NAMES.get(b[0], b[0])} (bal {b[1]['score']}) indi fikir bildirmir"
            elif not g["open"] and not (b[0] in EVENT_METHODS and g["reasons"] == [EVENT_REASON]):
                row["why"] = "risk qapısı bağlıdır: " + "; ".join(g["reasons"])
            else:
                row.update({"call": "AL" if f["p_up"] > 0.5 else "SAT", "p_up": f["p_up"],
                            "method": forecast.METHOD_NAMES.get(b[0], b[0]), "method_id": b[0],
                            "size": b[1]["size"], "cap": b[1]["cap"], "stage": b[1]["stage"],
                            "why": f"Avtomatik Hakim: bal {b[1]['score']}/100 ({b[1]['stage']}), ən zəif tərəf: "
                                   f"{b[1]['weakest']}"})
        else:
            f = db.execute("SELECT p_up, issued_t FROM forecasts WHERE symbol=? AND horizon=? AND method=? AND "
                           "mode='live' AND target_t > ? ORDER BY issued_t DESC LIMIT 1",
                           (symbol, h, verdict["method"], now)).fetchone()     # an expired forecast says nothing
            row["method"] = forecast.METHOD_NAMES.get(verdict["method"], verdict["method"]) + (
                f" ({verdict['condition']} şəraitində)" if verdict.get("condition") else "")
            if not f or f["p_up"] == 0.5:
                row["why"] = f"{row['method']} indi fikir bildirmir"
            elif not g["open"] and not (verdict["method"] in EVENT_METHODS and g["reasons"] == [EVENT_REASON]):
                row["why"] = "risk qapısı bağlıdır: " + "; ".join(g["reasons"])
            else:
                from . import autojudge
                full = ((__import__("json").loads(db.get(autojudge.KEY) or "{}").get("desks") or {})
                        .get(f"{symbol}:{h}") or {}).get(verdict["method"]) or {}
                row.update({"call": "AL" if f["p_up"] > 0.5 else "SAT", "p_up": f["p_up"], "method_id": verdict["method"],
                            "size": 1.0, "cap": full.get("cap", autojudge.MAX_SHARE), "stage": autojudge.FULL,
                            "why": f"{row['method']} sübutludur; risk qapısı açıqdır"})
        desks.append(row)
    terazi = db.execute("SELECT horizon, p_up FROM forecasts WHERE symbol=? AND method='terazi' AND mode='live' "
                        "AND issued_t > ? ORDER BY issued_t", (symbol, now - 86400)).fetchall()
    return {"symbol": symbol, "gate": g, "desks": desks,
            "terazi": {r["horizon"]: r["p_up"] for r in terazi}, "ts": now}
