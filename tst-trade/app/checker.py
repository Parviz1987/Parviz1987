"""Mənbə yoxlayıcısı (Block 17, from the research PDF: «count wrong or invented facts in brain outputs»).

Every brain answer (except web search, which brings its own sources) is checked against what the brain was given:
each number written in its text must appear in its input. A number that is not there is invented (a language model
must never be the source of a figure). The texts shown to the owner already drop such sentences (guard_numbers);
this agent COUNTS them per brain, so a brain that invents often is visible and can lose trust.
Probabilities and ids (the answer's structure) are not text and are not checked."""
from __future__ import annotations

import json
import re
import time

from .db import DB

NUM = re.compile(r"\d+(?:[.,]\d+)?")
SCHEMA = """
CREATE TABLE IF NOT EXISTS brain_checks (ts REAL NOT NULL, slot TEXT NOT NULL, texts INTEGER, invented INTEGER,
  sample TEXT);
CREATE INDEX IF NOT EXISTS brain_checks_ts ON brain_checks(ts);
"""


def _strings(x) -> list[str]:
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [s for k, v in x.items() if k not in ("id", "symbol", "url") for s in _strings(v)]
    if isinstance(x, list):
        return [s for v in x for s in _strings(v)]
    return []


def invented(text: str, given: str) -> list[str]:
    """Numbers in the text that are not in the input — allowing rounding (4012 for 4012.35, 0.4 for 0.42) and a
    fraction written as a percent (1.2 for 0.012): rounding is not invention (audit 2026-11-24: the strict check
    counted rounded levels as invented)."""
    known = []
    for n in NUM.findall(given):
        try:
            known.append(float(n.replace(",", ".")))
        except ValueError:
            pass
    ks = sorted(set(known))
    out = []
    for m in NUM.findall(text):
        try:
            x = float(m.replace(",", "."))
        except ValueError:
            continue
        if x < 10 and x == int(x):
            continue                      # small whole numbers: counts, days, «3 qayda» — not facts to check
        tol = max(abs(x) * 0.002, 0.5 * 10 ** -(len(m.split(".")[1]) if "." in m else 0))
        if not any(abs(x - k) <= tol or abs(x - 100 * k) <= tol for k in ks):
            out.append(m)
    return out


def record(db: DB, slot: str, data: dict | None, given: str, now: float | None = None) -> int:
    """Count the invented numbers in one answer and keep the count. Never raises."""
    try:
        db.script(SCHEMA)
        texts = _strings(data or {})
        bad = [n for t in texts for n in invented(t, given)]
        db.execute("INSERT INTO brain_checks VALUES(?,?,?,?,?)",
                   (time.time() if now is None else now, slot, len(texts), len(bad), json.dumps(bad[:8])))
        return len(bad)
    except Exception:
        return 0


def report(db: DB, days: int = 30) -> list[dict]:
    db.script(SCHEMA)
    out = []
    for r in db.execute("SELECT slot, COUNT(*) answers, SUM(invented > 0) bad_answers, SUM(invented) invented "
                        "FROM brain_checks WHERE ts > ? GROUP BY slot ORDER BY slot",
                        (time.time() - days * 86400,)).fetchall():
        d = dict(r)
        d["bad_share"] = (d["bad_answers"] or 0) / d["answers"] if d["answers"] else None
        out.append(d)
    return out
