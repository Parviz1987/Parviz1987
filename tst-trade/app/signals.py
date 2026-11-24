"""Sinirlər (the nerves): what just happened that should wake the analysis at once, instead of waiting for the hour.

A signal is written here by the part that saw it; the brain jobs read the pending ones and run the Strategist right
away with «what happened» in its facts (an alarm). Kinds:
- news     a headline the Reader rated strength 3 (a market mover: war, Fed, sanctions...)
- flow     2+ different events (not copies of one story) of strength 2+, same metal and direction, within 15 min
- release  a US figure whose actual was confirmed (two brains agreed, or the calendar had it)
- move     a 15-minute move of a metal or a linked market 4x bigger than its usual move of the last 2 days
- band     the price left our own 1-hour 80 % range: our prediction failed (nerve.py, prediction-error alarm)
Every signal has a unique id, so the same event never alarms twice. See docs/sinir-sistemi.md."""
from __future__ import annotations

import time

from . import candles
from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, uid TEXT UNIQUE, ts REAL NOT NULL, kind TEXT NOT NULL,
  metal TEXT, strength INTEGER, text TEXT, handled_ts REAL);
CREATE INDEX IF NOT EXISTS signals_ts ON signals(ts);
"""
FRESH = 1800            # a signal older than this is history, not an alarm
MOVE_X, MOVE_MIN = 4.0, 0.0025   # x usual move, and at least 0.25 %
MOVE_ALARMS_PER_DAY = 4          # price moves may use at most this many of the day's alarms: news and figures keep the rest
NAMES = {"XAU": "Qızıl", "XAG": "Gümüş", "XPT": "Platin", "XPD": "Palladium", "DXY": "Dollar indeksi",
         "EURUSD": "EUR/USD", "USDJPY": "USD/JPY", "OIL": "Neft (WTI)", "BRENT": "Neft (Brent)", "US500": "S&P 500",
         "VIX": "VIX", "US10Y": "ABŞ 10 illik istiqraz"}


def ensure(db: DB) -> None:
    db.script(SCHEMA)


def emit(db: DB, uid: str, kind: str, text: str, strength: int = 2, metal: str | None = None,
         now: float | None = None) -> bool:
    now = time.time() if now is None else now
    cur = db.execute("INSERT OR IGNORE INTO signals(uid, ts, kind, metal, strength, text) VALUES(?,?,?,?,?,?)",
                     (uid, now, kind, metal, strength, text[:300]))
    return cur.rowcount > 0


def _table(db: DB, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def from_news(db: DB, now: float) -> int:
    if not _table(db, "news_ai"):
        return 0
    n = 0
    from . import newsevents
    newsevents.ensure(db)
    rows = db.execute("SELECT a.uid, a.ts, a.metals, a.direction, a.strength, n.title, e.event_id FROM news_ai a "
                      "JOIN news n ON n.uid = a.uid LEFT JOIN news_event e ON e.uid = a.uid "
                      "WHERE a.ts > ? AND a.strength >= 2 AND a.direction != 'neutral' "
                      "ORDER BY a.ts", (now - 900,)).fetchall()
    flows: dict[tuple[str, str], dict] = {}
    for r in rows:
        metals = [m for m in (r["metals"] or "").split(",") if m]
        key = f"ev{r['event_id']}" if r["event_id"] is not None else r["uid"]    # Block 17: one story, one alarm
        if r["strength"] >= 3:
            n += emit(db, "news:" + key, "news", f"Güclü xəbər ({r['direction']}): {r['title']}", 3,
                      ",".join(metals) or None, now)
        for m in metals:
            flows.setdefault((m, r["direction"]), {})[key] = r["title"]
    for (m, d), by_event in flows.items():
        titles = list(by_event.values())          # distinct events: a copied story is counted once
        if len(titles) >= 2:
            n += emit(db, f"flow:{m}:{d}:{int(now // 900)}", "flow",
                      f"{NAMES.get(m, m)}: 15 dəqiqədə {len(titles)} güclü xəbər, istiqamət {d}: {titles[-1]}", 2, m, now)
    return n


def from_releases(db: DB, now: float) -> int:
    if not _table(db, "releases"):
        return 0
    cols = {r[1] for r in db.execute("PRAGMA table_info(releases)").fetchall()}
    when = "known_ts" if "known_ts" in cols else "ts"
    n = 0
    for r in db.execute(f"SELECT uid, event, estimate, actual FROM releases WHERE actual IS NOT NULL AND {when} > ?",
                        (now - FRESH,)).fetchall():
        n += emit(db, "release:" + r["uid"], "release",
                  f"ABŞ rəqəmi çıxdı: {r['event']} — fakt {r['actual']}, gözlənti {r['estimate']}", 3, None, now)
    return n


def from_moves(db: DB, now: float, symbols: list[str]) -> int:
    n = 0
    for sym in symbols:
        rows = candles.closed(db, sym, "15m", now, limit=193)
        if len(rows) < 50 or rows[-1]["t"] < now - 1800:
            continue
        rets = [abs(b["c"] / a["c"] - 1) for a, b in zip(rows, rows[1:]) if a["c"] and b["t"] - a["t"] == 900]
        if len(rets) < 40:
            continue
        moved = sorted(r for r in rets[:-1] if r > 0)      # flat candles (market closed, holiday) are not «usual»
        if len(moved) < 30:
            continue
        usual = moved[int(len(moved) * 0.75)]       # the upper quartile: quiet night hours must not make
                                                     # an ordinary day-time move look like a shock
        last = rows[-1]["c"] / rows[-2]["c"] - 1 if rows[-2]["c"] else 0
        from .nerve import move_factor
        if abs(last) >= max(MOVE_X * usual * move_factor(db), MOVE_MIN):
            n += emit(db, f"move:{sym}:{rows[-1]['t']}", "move",
                      f"{NAMES.get(sym, sym)} 15 dəqiqədə {last * 100:+.2f} % tərpəndi (adi hərəkət {usual * 100:.2f} %)",
                      3 if abs(last) >= 2 * MOVE_X * usual else 2, sym, now)
    return n


def scan(db: DB, now: float, symbols: list[str]) -> int:
    ensure(db)
    return from_news(db, now) + from_releases(db, now) + from_moves(db, now, symbols)


REFRACTORY = 60 * 60     # the same kind on the same metal alarms at most once an hour (habituation)


def pending(db: DB, now: float) -> list[dict]:
    """Unhandled fresh signals, after the attention filter (thalamus): a signal of the same kind on the same metal as
    one handled in the last hour is let go quietly (marked handled, no alarm) — repeated news on one story does not
    wake the brains again and again. A strong one (strength 3) always passes."""
    ensure(db)
    out = []
    for r in db.execute("SELECT * FROM signals WHERE handled_ts IS NULL AND ts > ? ORDER BY ts", (now - FRESH,)).fetchall():
        r = dict(r)
        if r["strength"] < 3 and db.execute(
                "SELECT 1 FROM signals WHERE kind=? AND IFNULL(metal,'')=IFNULL(?,'') AND handled_ts > ? AND id != ?",
                (r["kind"], r["metal"], now - REFRACTORY, r["id"])).fetchone():
            db.execute("UPDATE signals SET handled_ts=? WHERE id=?", (now, r["id"]))
            continue
        out.append(r)
    return out


def mark(db: DB, ids: list[int], now: float) -> None:
    db.executemany("UPDATE signals SET handled_ts=? WHERE id=?", [(now, i) for i in ids])


def recent(db: DB, limit: int = 15) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.execute("SELECT ts, kind, metal, strength, text, handled_ts FROM signals "
                                        "ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()]
