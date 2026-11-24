"""Sinir sisteminin nüvəsi (Block 10): reflex, state, and the three global signals, modelled on the nervous system.

- Reflex (spinal reflex: acts before the brain): on every metal price, a jump larger than REFLEX_JUMP within one minute
  closes that metal at once for REFLEX_HOLD seconds — the decision says GÖZLƏ immediately; no brain is asked first.
  It reopens only after the hold has passed without a new jump (hysteresis).
- Three global signals (neuromodulators), recomputed every minute:
  arousal     — how wild the last hour is: the percentile of its 15-minute moves against the last 60 days (0..1);
  uncertainty — how much the brains disagree: the spread of the latest 1-hour P(up) of the Strategist, the second
                brain and the debate (0 = agree);
  surprise    — how far the price stands from our own 1-hour forecast: (price - centre) / half-width of the 80 % range
                (|z| > 1 = outside the range: the prediction failed — a prediction-error alarm fires).
- State (autonomic system): SAKİT (rest) / DİQQƏT (attention: wild market, brains disagree, or the price left our
  range) / HƏYƏCAN (alarm: an alarm was handled in the last 45 minutes). HƏYƏCAN decays by itself.
  Effects: in HƏYƏCAN the Strategist runs every 30 minutes instead of 60; the price-move alarm needs a bigger move when
  arousal is high (no alarm storms in a wild market)."""
from __future__ import annotations

import json
import time

from . import candles
from .db import DB

REFLEX_JUMP = {"XAU": 0.003, "XAG": 0.006, "XPT": 0.006, "XPD": 0.008}   # one-minute jump that closes the metal
REFLEX_HOLD = 300
ALARM_DECAY = 45 * 60


class Reflex:
    def __init__(self):
        from collections import deque
        self._deque = deque
        self.until: dict[str, float] = {}
        self.why: dict[str, str] = {}
        self.seen: dict[str, "deque"] = {}            # symbol -> recent (ts, price), the last ~70 seconds

    def feel(self, symbol: str, now: float, price: float | None) -> None:
        if not price or symbol not in REFLEX_JUMP:
            return
        d = self.seen.setdefault(symbol, self._deque())
        d.append((now, price))
        while d and now - d[0][0] > 70:
            d.popleft()
        base = next((p for t, p in d if now - t <= 60), None)
        move = price / base - 1 if base else 0
        if abs(move) >= REFLEX_JUMP[symbol]:
            self.until[symbol] = now + REFLEX_HOLD
            self.why[symbol] = f"refleks: 1 dəqiqədə {move * 100:+.2f} % sıçrayış"

    def closed(self, symbol: str, now: float | None = None) -> str | None:
        now = time.time() if now is None else now
        return self.why.get(symbol) if self.until.get(symbol, 0) > now else None


def _arousal(db: DB, now: float) -> float | None:
    rows = candles.closed(db, "XAU", "15m", now, limit=60 * 24 * 4 // 6)
    rets = [abs(b["c"] / a["c"] - 1) for a, b in zip(rows, rows[1:]) if a["c"] and b["t"] - a["t"] == 900]
    if len(rets) < 200:
        return None
    hour = sum(rets[-4:]) / 4
    hist = sorted(sum(rets[i:i + 4]) / 4 for i in range(0, len(rets) - 4))
    return round(sum(x < hour for x in hist) / len(hist), 3)


def _uncertainty(db: DB, now: float, metal: str = "XAU") -> float | None:
    from . import brainviews
    brainviews.ensure(db)
    ps = []
    for src in ("strateq", "brain2", "debate"):
        r = db.execute("SELECT p FROM brain_views WHERE source=? AND metal=? AND horizon='1h' AND p IS NOT NULL AND "
                       "COALESCE(known_ts, ts) > ? ORDER BY COALESCE(known_ts, ts) DESC LIMIT 1",
                       (src, metal, now - 2 * 3600)).fetchone()
        if r:
            ps.append(r["p"])
    if len(ps) < 2:
        return None
    return round(max(ps) - min(ps), 3)


def _surprise(db: DB, now: float, metal: str = "XAU") -> tuple[float | None, int | None]:
    f = db.execute("SELECT issued_t, lo80, hi80 FROM forecasts WHERE symbol=? AND horizon='1h' AND method='rw' AND "
                   "mode='live' AND target_t > ? ORDER BY issued_t DESC LIMIT 1", (metal, now)).fetchone()
    px = db.execute("SELECT c FROM candles WHERE symbol=? AND tf='1m' ORDER BY t DESC LIMIT 1", (metal,)).fetchone()
    if not f or not px or f["hi80"] <= f["lo80"]:
        return None, None
    centre, half = (f["hi80"] + f["lo80"]) / 2, (f["hi80"] - f["lo80"]) / 2
    return round((px["c"] - centre) / half, 2), f["issued_t"]


def update(db: DB, now: float | None = None) -> dict:
    """Recompute the three signals and the state (every minute, off the event loop). Fires the prediction-error alarm
    for any metal whose price has left our own 1-hour 80 % range (once per forecast)."""
    from . import signals
    now = time.time() if now is None else now
    mod = {"arousal": _arousal(db, now), "uncertainty": _uncertainty(db, now), "ts": now, "surprise": {}}
    for m in ("XAU", "XAG", "XPT", "XPD"):
        z, issued = _surprise(db, now, m)
        mod["surprise"][m] = z
        if z is not None and abs(z) > 1:
            signals.ensure(db)
            signals.emit(db, f"band:{m}:{issued}", "band",
                         f"{signals.NAMES.get(m, m)} öz proqnozumuzun 80 % koridorundan çıxdı (z = {z:+.1f})",
                         3 if abs(z) > 1.5 else 2, m, now)
    last_alarm = float(db.get("alarm:last") or 0)
    if now - last_alarm < ALARM_DECAY:
        state, why = "HƏYƏCAN", f"həyəcan {int((now - last_alarm) // 60)} dəq əvvəl"
    elif (mod["arousal"] or 0) >= 0.9 or (mod["uncertainty"] or 0) >= 0.2 or \
            any(z is not None and abs(z) > 1 for z in mod["surprise"].values()):
        reasons = []
        if (mod["arousal"] or 0) >= 0.9:
            reasons.append("bazar çox dalğalıdır")
        if (mod["uncertainty"] or 0) >= 0.2:
            reasons.append("beyinlər razı deyil")
        if any(z is not None and abs(z) > 1 for z in mod["surprise"].values()):
            reasons.append("qiymət proqnoz koridorundan çıxıb")
        state, why = "DİQQƏT", ", ".join(reasons)
    else:
        state, why = "SAKİT", "hər şey gözləntidədir"
    prev = json.loads(db.get("nerve:state") or "{}")
    since = prev.get("since", now) if prev.get("state") == state else now
    out = {"state": state, "why": why, "since": since, "mod": mod}
    db.put("nerve:state", json.dumps(out))
    return out


def state(db: DB) -> dict:
    return json.loads(db.get("nerve:state") or '{"state": "SAKİT", "why": "hələ hesablanmayıb", "mod": {}}')


def move_factor(db: DB) -> float:
    """Neuromodulation of the price-move alarm: a wild market needs a bigger move to alarm."""
    a = (state(db).get("mod") or {}).get("arousal")
    return 1.5 if a is not None and a >= 0.9 else 1.0
