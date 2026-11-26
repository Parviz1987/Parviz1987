"""Təmizlik (owner 2026-11-26: «clean the wrong data, the unneeded data, whatever is left over — you may delete»).

The forecast archive of the RETIRED methods (momentum, RSI, Fibonacci, breakout, the old impulses, the session
method ...: each became a rule of a block and left the forecasts) was more than half of the database and is read by
nothing. Before it goes, each method's final record is kept (per metal, horizon and mode: forecasts, hits, Brier,
80 % range coverage) in kv «archive:retired», so «how did that method do?» still has its answer. The replayed history
rows go in small batches (the site never waits); the few live rows stay as they were issued."""
from __future__ import annotations

import json
import time

from .db import DB

MARK = "cleanup:retired_v1"
BATCH = 20000


def snapshot(db: DB, methods: tuple[str, ...]) -> list[dict]:
    q = ",".join("?" * len(methods))
    rows = db.execute(
        f"SELECT method, symbol, horizon, mode, COUNT(*) n, COUNT(hit) nh, SUM(hit) hits, AVG(brier) brier, "
        f"AVG(in80) cover80, MIN(issued_t) t0, MAX(issued_t) t1 FROM forecasts WHERE method IN ({q}) "
        f"GROUP BY method, symbol, horizon, mode", methods).fetchall()
    return [{**dict(r), "hit_rate": round(r["hits"] / r["nh"], 4) if r["nh"] else None,
             "brier": None if r["brier"] is None else round(r["brier"], 5),
             "cover80": None if r["cover80"] is None else round(r["cover80"], 4)} for r in rows]


def retired_archive(db: DB, pause: float = 0.2) -> dict:
    """Once: keep the record, then delete the replayed history of the retired methods. Returns what was done."""
    if db.get(MARK):
        return json.loads(db.get(MARK))
    from .forecast import METHODS, RETIRED
    gone = tuple(m for m in RETIRED if m not in METHODS)
    if not gone:
        return {}
    snap = snapshot(db, gone)
    prev = json.loads(db.get("archive:retired") or "[]")
    db.put("archive:retired", json.dumps(prev + [{"ts": time.time(), "rows": snap}], ensure_ascii=False))
    q = ",".join("?" * len(gone))
    deleted = 0
    while True:
        n = db.execute(f"DELETE FROM forecasts WHERE id IN (SELECT id FROM forecasts WHERE mode='history' AND method IN "
                       f"({q}) LIMIT {BATCH})", gone).rowcount
        deleted += max(n, 0)
        if n < BATCH:
            break
        time.sleep(pause)               # let the price step and the site write in between
    out = {"ts": time.time(), "methods": list(gone), "deleted": deleted, "kept_record": len(snap)}
    db.put(MARK, json.dumps(out))
    return out


VACUUM_AT = 1795753800        # 2026-11-27 04:30 UTC: right after DigitalOcean's daily backup (owner approved «ha ed»)
VACUUM_MARK = "cleanup:vacuum_v1"


def vacuum_due(db: DB, now: float | None = None) -> bool:
    return (time.time() if now is None else now) >= VACUUM_AT and not db.get(VACUUM_MARK)


def vacuum(db: DB) -> dict:
    """Once: give the space freed by the clean-up back to the disk (the file shrinks). Writes wait meanwhile; reads
    go on. The size before and after and the time it took are kept for the diagnostics."""
    import os
    before = os.path.getsize(db.path) if db.path != ":memory:" else 0
    t0 = time.time()
    db.execute("PRAGMA busy_timeout=60000")      # wait for a reader to finish rather than fail
    db.execute("VACUUM")
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    after = os.path.getsize(db.path) if db.path != ":memory:" else 0
    out = {"ts": time.time(), "mb_before": round(before / 1e6), "mb_after": round(after / 1e6),
           "seconds": round(time.time() - t0, 1)}
    db.put(VACUUM_MARK, json.dumps(out))
    return out


def run(db: DB) -> dict:
    return {"retired": retired_archive(db)}
