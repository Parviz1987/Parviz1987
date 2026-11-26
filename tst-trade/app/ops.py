"""Avtomatik təmirin «Dayandır» düyməsi (owner 2026-11-26, plan step 4): one switch in Admin. While it is pressed,
nothing changes the system on its own: the repair catalogue (plan step 4) takes no step, and the 3-hour Claude duty
check only reads and reports (it sees the switch in the diagnostics). The outside watcher keeps watching. Pressing it
or releasing it is written to the security log with the time and the address."""
from __future__ import annotations

import json
import time

from .db import DB

KEY = "ops:paused"


def paused(db: DB) -> bool:
    try:
        return bool(json.loads(db.get(KEY) or "null"))
    except ValueError:
        return True                    # an unreadable switch is treated as pressed: the safe side


def state(db: DB) -> dict:
    try:
        v = json.loads(db.get(KEY) or "null")
    except ValueError:
        v = {"on": True, "ts": None}
    return {"paused": bool(v), "since": (v or {}).get("ts") if isinstance(v, dict) else None}


def set_paused(db: DB, on: bool) -> dict:
    db.put(KEY, json.dumps({"on": True, "ts": time.time()}) if on else "null")
    return state(db)
