"""Hadisə birləşdiricisi (Block 17): the same story written by five sites is ONE event, not five confirmations.

Each new headline gets an event number. A headline whose words overlap enough (Jaccard >= SAME) with a headline of an
event seen in the last WINDOW hours joins that event; otherwise it opens a new one. Then:
- the Reader rates only the first headline of an event (no paying five times for one story);
- the nerves count events, not headlines (a «flow» needs two different events, not one story copied).
Simple word overlap, no brain: cheap, fast and its decisions can be checked by eye."""
from __future__ import annotations

import re
import time

from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS news_event (uid TEXT PRIMARY KEY, event_id INTEGER NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS news_event_e ON news_event(event_id);
CREATE INDEX IF NOT EXISTS news_event_ts ON news_event(ts);
"""
SAME, WINDOW = 0.45, 12 * 3600
STOP = {"the", "and", "for", "with", "from", "that", "this", "after", "over", "into", "amid", "as", "on", "in", "of",
        "to", "a", "an", "is", "are", "be", "by", "at", "its", "it", "says", "say", "said", "new", "news", "live",
        "update", "updates", "price", "prices", "today", "report", "reports"}


def ensure(db: DB) -> None:
    db.script(SCHEMA)


def words(title: str) -> frozenset:
    title = re.sub(r"\s[-|–]\s[^-|–]{2,40}$", "", title or "")          # drop « - Reuters» style site tails
    return frozenset(w for w in re.findall(r"[a-zA-Zа-яА-ЯəğıöşüçƏĞIÖŞÜÇ0-9]+", title.lower())
                     if len(w) > 2 and w not in STOP)


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def assign(db: DB, now: float | None = None) -> dict:
    """Give every new headline (last 24 h) its event number. Returns {"headlines": n, "new_events": k}."""
    ensure(db)
    now = time.time() if now is None else now
    new = db.execute("SELECT n.uid, n.title, n.ts FROM news n LEFT JOIN news_event e ON e.uid = n.uid "
                     "WHERE e.uid IS NULL AND n.ts > ? ORDER BY n.ts", (now - 86400,)).fetchall()
    if not new:
        return {"headlines": 0, "new_events": 0}
    known = [(r["event_id"], r["ts"], words(r["title"])) for r in db.execute(
        "SELECT e.event_id, n.ts, n.title FROM news_event e JOIN news n ON n.uid = e.uid WHERE n.ts > ?",
        (now - 86400 - WINDOW,)).fetchall()]
    nxt = (db.execute("SELECT MAX(event_id) m FROM news_event").fetchone()["m"] or 0) + 1
    rows, opened = [], 0
    for r in new:
        w = words(r["title"])
        best, best_j = None, 0.0
        for eid, ts, kw in known:
            if abs(r["ts"] - ts) <= WINDOW:
                j = jaccard(w, kw)
                if j > best_j:
                    best, best_j = eid, j
        if best is None or best_j < SAME:
            best, nxt, opened = nxt, nxt + 1, opened + 1
        known.append((best, r["ts"], w))
        rows.append((r["uid"], best, r["ts"]))
    db.executemany("INSERT OR IGNORE INTO news_event(uid, event_id, ts) VALUES(?,?,?)", rows)
    return {"headlines": len(rows), "new_events": opened}


def day_counts(db: DB, now: float | None = None) -> dict:
    ensure(db)
    now = time.time() if now is None else now
    r = db.execute("SELECT COUNT(*) h, COUNT(DISTINCT event_id) e FROM news_event WHERE ts > ?", (now - 86400,)).fetchone()
    return {"headlines": r["h"], "events": r["e"]}
