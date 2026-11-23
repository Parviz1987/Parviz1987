"""US data surprises: the released figure against the economists' estimate, and what it usually means for gold.

Source: the FMP economic calendar (owner's key): every US release with estimate, previous and actual. A figure above
the estimate in inflation, jobs or growth makes the Fed less likely to cut and the dollar stronger: usually bad for
gold. Unemployment and jobless claims work the other way. The sign is only a hypothesis: the Judge measures it.

Look-ahead rule: a forecast issued at time t sees only releases dated at least 60 seconds before t."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS releases (uid TEXT PRIMARY KEY, ts REAL NOT NULL, event TEXT NOT NULL, impact TEXT,
  estimate REAL, previous REAL, actual REAL, raw_date TEXT);
CREATE INDEX IF NOT EXISTS releases_ts ON releases(ts);
"""
FMP_URL = "https://financialmodelingprep.com/stable/economic-calendar"

# (pattern, gold direction when the figure comes in ABOVE the estimate)
RULES = [
    (r"unemployment rate|unemployment claims|jobless claims|initial claims|continuing claims", +1),
    (r"\bcpi\b|consumer price|\bppi\b|producer price|\bpce\b|price index|inflation", -1),
    (r"non[- ]?farm|payroll|employment change|\badp\b", -1),
    (r"\bgdp\b|retail sales|\bism\b|\bpmi\b|durable goods|industrial production|consumer confidence|"
     r"michigan|sentiment|jolts|job openings|housing starts|building permits|new home sales|existing home", -1),
    (r"interest rate decision|fed funds|federal funds", -1),
]
WINDOW = {"15m": 15 * 60, "30m": 30 * 60, "1h": 3600, "4h": 4 * 3600, "1d": 86400}
WEIGHT = {"High": 1.0, "Medium": 0.5}


def gold_direction(event: str) -> int:
    e = event.lower()
    for rx, d in RULES:
        if re.search(rx, e):
            return d
    return 0


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace(",", "")
    mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(t[-1:].upper(), 1)
    t = t.rstrip("%KMBTkmbt")
    try:
        return float(t) * mult
    except ValueError:
        return None


def parse_fmp(data) -> list[dict]:
    """FMP rows -> US releases. FMP dates are UTC ("2026-11-13 13:30:00")."""
    rows = json.loads(data) if isinstance(data, (bytes, str)) else data
    if isinstance(rows, dict):    # an error message instead of a list
        raise ValueError("FMP: " + str(rows.get("Error Message") or rows.get("message") or rows)[:160])
    if not isinstance(rows, list):
        raise ValueError("FMP: gözlənilməyən cavab")
    out = []
    for r in rows:
        if not isinstance(r, dict) or str(r.get("country", "")).upper() not in ("US", "USA", "UNITED STATES"):
            continue
        ev, raw = str(r.get("event") or "").strip(), str(r.get("date") or "").strip()
        if not ev or not raw:
            continue
        try:
            ts = datetime.fromisoformat(raw.replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
        out.append({"uid": hashlib.sha1(f"{ev}|{raw}".encode()).hexdigest()[:20], "ts": ts, "event": ev[:120],
                    "impact": str(r.get("impact") or "").title(), "estimate": _num(r.get("estimate")),
                    "previous": _num(r.get("previous")), "actual": _num(r.get("actual")), "raw_date": raw[:25]})
    return out


def ensure(db: DB) -> None:
    """Schema, plus known_ts: when a figure became known here (a figure found by the brains minutes after the release
    must not be used by a forecast issued before it was found)."""
    db.conn.executescript(SCHEMA)
    cols = {r[1] for r in db.execute("PRAGMA table_info(releases)").fetchall()}
    if "known_ts" not in cols:
        db.execute("ALTER TABLE releases ADD COLUMN known_ts REAL")


def store(db: DB, rows: list[dict]) -> None:
    ensure(db)
    rows = [{"known_ts": None, **r} for r in rows]
    db.executemany("INSERT INTO releases(uid, ts, event, impact, estimate, previous, actual, raw_date, known_ts) "
                   "VALUES(:uid, :ts, :event, :impact, :estimate, :previous, :actual, :raw_date, :known_ts) "
                   "ON CONFLICT(uid) DO UPDATE SET estimate=excluded.estimate, previous=excluded.previous, "
                   "actual=excluded.actual, impact=excluded.impact", rows)


def surprise_of(r) -> dict | None:
    """One release -> its surprise and what it points to for gold (None: not a scored release)."""
    d = gold_direction(r["event"])
    w = WEIGHT.get(r["impact"] or "", 0)
    if not d or not w or r["actual"] is None or r["estimate"] is None or r["actual"] == r["estimate"]:
        return None
    above = r["actual"] > r["estimate"]
    seen = r["known_ts"] if "known_ts" in r.keys() and r["known_ts"] else r["ts"]
    return {"event": r["event"], "ts": max(r["ts"], seen), "actual": r["actual"], "estimate": r["estimate"],
            "above": above, "gold": d if above else -d, "weight": w}


class Lookup:
    """All scored releases in memory, for fast windows (live and the history replay)."""

    def __init__(self, db: DB):
        try:
            ensure(db)
            rows = db.execute("SELECT ts, event, impact, estimate, actual, known_ts FROM releases "
                              "WHERE actual IS NOT NULL").fetchall()
        except Exception:
            rows = []
        self.items = sorted((s for s in (surprise_of(r) for r in rows) if s), key=lambda s: s["ts"])
        self.ts = [s["ts"] for s in self.items]
        self.first = self.items[0]["ts"] if self.items else None

    def window(self, t: float, horizon: str) -> list[dict] | None:
        """Releases in [t - window, t - 60]; None when the data does not reach back to t (no view, not 'no news')."""
        w = WINDOW.get(horizon)
        if horizon == "1d":
            t -= 7200     # a daily candle labelled D is forecast at 22:00 UTC the evening before
        if w is None or self.first is None or t < self.first:
            return None
        import bisect
        lo, hi = bisect.bisect_left(self.ts, t - w), bisect.bisect_right(self.ts, t - 60)
        return self.items[lo:hi]


def recent(db: DB, now: float, limit: int = 8) -> list[dict]:
    rows = db.execute("SELECT ts, event, impact, estimate, previous, actual FROM releases WHERE ts <= ? AND "
                      "impact IN ('High', 'Medium') ORDER BY ts DESC LIMIT ?", (now, limit)).fetchall()
    out = []
    for r in rows:
        s = surprise_of(r)
        out.append({**dict(r), "gold": s["gold"] if s else 0, "scored": bool(s)})
    return out
