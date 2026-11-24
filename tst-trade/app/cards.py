"""Proqnoz kartı (Block 16, owner 2026-11-24): every Strategist forecast is frozen at the moment it is given, with
everything needed later to understand it, and never edited or deleted:
- the instrument, the moment (when the answer arrived) and the price then, the horizon;
- the main scenario (why), the counter-scenario and the condition that would weaken it (from the brain);
- the probability: the brain's number and, where the brain is calibrated (30+ cases in that band), the calibrated
  one; otherwise «ölçülməyib» (not measured);
- the 80 % range for that horizon (our rw range) and how often that range really held (Judge coverage);
- data quality at that moment: which inputs were missing or stale (computed by the system, not by the brain);
- when the forecast should be renewed;
- the version: the code commit, the model that answered and a short fingerprint of the instructions.
When the horizon has passed, the card gets what really happened (price, up/down, right/wrong) — added, never changed."""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS forecast_cards (id INTEGER PRIMARY KEY, known_ts REAL NOT NULL, metal TEXT NOT NULL,
  horizon TEXT NOT NULL, source TEXT NOT NULL, price0 REAL, p REAL, p_cal REAL, lo80 REAL, hi80 REAL, cover80 REAL,
  scenario TEXT, counter TEXT, invalidation TEXT, next_update TEXT, quality TEXT, version TEXT, model TEXT,
  prompt_hash TEXT, chain TEXT, price1 REAL, result TEXT, scored_ts REAL, rules TEXT);
CREATE INDEX IF NOT EXISTS forecast_cards_m ON forecast_cards(metal, known_ts);
"""
H_SEC = {"1h": 3600, "4h": 4 * 3600, "1d": 86400}
_VERSION: str | None = None     # read at the first card; the server restarts on every update, so it is the running code


def ensure(db: DB) -> None:
    db.script(SCHEMA)
    if "rules" not in {r[1] for r in db.execute("PRAGMA table_info(forecast_cards)").fetchall()}:
        db.execute("ALTER TABLE forecast_cards ADD COLUMN rules TEXT")      # Block 27: the rules a view rests on


def version() -> str:
    """The code commit the server runs (read once)."""
    global _VERSION
    if _VERSION is None:
        try:
            _VERSION = subprocess.run(["git", "-C", str(Path(__file__).resolve().parent.parent), "rev-parse", "--short",
                                       "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip() or "?"
        except Exception:
            _VERSION = "?"
    return _VERSION


def prompt_hash(system: str) -> str:
    return hashlib.sha256(system.encode()).hexdigest()[:10]


def quality(facts: dict) -> list[str]:
    """What was missing or stale in the facts the brain got (system-computed, honest about gaps)."""
    issues = []
    moves = facts.get("moves_pct") or {}
    for m in ("XAU", "XAG", "XPT", "XPD"):
        if m not in moves:
            issues.append(f"{m}: son hərəkət yoxdur")
    for code in ("DXY", "US10Y", "OIL"):
        if code not in moves:
            issues.append(f"{code}: bazar məlumatı yoxdur")
    if not facts.get("macro"):
        issues.append("makro göstəricilər yoxdur")
    if not facts.get("fed_odds_kalshi"):
        issues.append("Fed ehtimalları (Kalshi) yoxdur")
    if not facts.get("news"):
        issues.append("son 24 saatda güclü xəbər yoxdur")
    return issues


def _rw_range(db: DB, metal: str, horizon: str) -> tuple:
    r = db.execute("SELECT lo80, hi80 FROM forecasts WHERE symbol=? AND horizon=? AND mode='live' AND method='rw' "
                   "ORDER BY issued_t DESC LIMIT 1", (metal, horizon)).fetchone()
    return (r["lo80"], r["hi80"]) if r else (None, None)


def _price(db: DB, metal: str, t: float) -> float | None:
    r = db.execute("SELECT c FROM candles WHERE symbol=? AND tf='1m' AND t<=? AND t>? ORDER BY t DESC LIMIT 1",
                   (metal, t - 60, t - 1800)).fetchone()
    return r["c"] if r else None


def freeze(db: DB, now: float, source: str, data: dict, how: str, facts_json: str, system: str,
           chain: str = "") -> int:
    """One card per metal and horizon from a brain's answer. Returns the number of cards written."""
    from . import judge, learning
    from .brainjobs import guard_numbers
    ensure(db)
    try:
        facts = json.loads(facts_json)
    except ValueError:
        facts = {}
    q = json.dumps(quality(facts), ensure_ascii=False)
    try:
        bands = json.loads(db.get("calib") or "{}").get("bands", {})
    except ValueError:
        bands = {}
    model = how.split(" · ", 1)[-1] if how else "?"
    ph, ver = prompt_hash(system), version()
    rows = []
    for m in data.get("metals", []):
        sym = m.get("symbol")
        if sym not in ("XAU", "XAG", "XPT", "XPD"):
            continue
        g = lambda k: guard_numbers(str(m.get(k, "") or ""), facts_json)[:300]
        for h, key in (("1h", "p1h"), ("4h", "p4h"), ("1d", "p1d")):
            try:
                p = float(m.get(key))
            except (TypeError, ValueError):
                continue
            if not 0 <= p <= 1:
                continue
            cal = None
            for lo, hi, obs, n in bands.get(f"{source}:{h}", []):
                if lo <= p < hi and n >= 30:
                    cal = learning.apply_calibration(bands, source, h, p)
                    break
            lo80, hi80 = _rw_range(db, sym, h)
            st = {r["method"]: r for r in judge.stats(db, sym, h, "live", ttl=600)}
            cover = (st.get("rw") or {}).get("cover80")
            from .playbook import BY_ID
            cited = ",".join(r for r in (m.get("rules") or []) if isinstance(r, str) and r in BY_ID)
            rows.append((now, sym, h, source, _price(db, sym, now), p, cal, lo80, hi80, cover, g("why"), g("counter"),
                         g("invalidation"), g("next_update"), q, ver, model, ph, chain, cited))
    db.executemany("INSERT INTO forecast_cards(known_ts, metal, horizon, source, price0, p, p_cal, lo80, hi80, cover80, "
                   "scenario, counter, invalidation, next_update, quality, version, model, prompt_hash, chain, rules) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def score(db: DB, now: float | None = None) -> int:
    """Add what really happened to every card whose horizon has passed (once; the card itself is never changed)."""
    ensure(db)
    now = time.time() if now is None else now
    n = 0
    for r in db.execute("SELECT id, known_ts, metal, horizon, price0, p FROM forecast_cards WHERE scored_ts IS NULL "
                        "AND known_ts < ?", (now - 3600,)).fetchall():
        end = r["known_ts"] + H_SEC.get(r["horizon"], 0)
        if end > now:
            continue
        b = _price(db, r["metal"], end)
        if b is None or not r["price0"]:
            res = "ölçülmədi"            # no price then (market closed): honest, not guessed
        elif b == r["price0"] or abs(r["p"] - 0.5) < 0.02:
            res = "istiqamətsiz"
        else:
            res = "düz" if (b > r["price0"]) == (r["p"] > 0.5) else "səhv"
        db.execute("UPDATE forecast_cards SET price1=?, result=?, scored_ts=? WHERE id=?", (b, res, now, r["id"]))
        n += 1
    return n


def recent(db: DB, metal: str | None = None, limit: int = 30) -> list[dict]:
    ensure(db)
    q = "SELECT * FROM forecast_cards" + (" WHERE metal=?" if metal else "") + " ORDER BY known_ts DESC LIMIT ?"
    out = []
    for r in db.execute(q, ((metal, limit) if metal else (limit,))).fetchall():
        d = dict(r)
        try:
            d["quality"] = json.loads(d["quality"] or "[]")
        except ValueError:
            d["quality"] = []
        out.append(d)
    return out


def summary(db: DB, days: int = 30) -> dict:
    """Right / wrong per source and horizon over the scored cards (a first look; the Judge has the proof rules)."""
    ensure(db)
    out: dict[str, dict] = {}
    for r in db.execute("SELECT source, horizon, result, COUNT(*) n FROM forecast_cards WHERE scored_ts IS NOT NULL "
                        "AND known_ts > ? GROUP BY source, horizon, result", (time.time() - days * 86400,)).fetchall():
        d = out.setdefault(f"{r['source']}:{r['horizon']}", {})
        d[r["result"]] = r["n"]
    return out


def rule_record(db: DB, days: int = 90) -> dict:
    """Block 28: how the brains' forecasts turned out per rule they cited: {rule: {source: [right, wrong]}}."""
    ensure(db)
    out: dict = {}
    for r in db.execute("SELECT source, rules, result FROM forecast_cards WHERE scored_ts IS NOT NULL AND rules != '' "
                        "AND result IN ('düz', 'səhv') AND known_ts > ?", (time.time() - days * 86400,)).fetchall():
        for rule in (r["rules"] or "").split(","):
            if rule:
                c = out.setdefault(rule, {}).setdefault(r["source"], [0, 0])
                c[0 if r["result"] == "düz" else 1] += 1
    return out
