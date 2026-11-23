"""Brain slots. A slot is defined by its job (registry.BRAIN_SLOTS); the brain in it is a setting the owner changes
on the admin page. In this first version no slot takes part in forecasts yet: the forecast desks are code, and each
slot is connected and measured by the Judge in its own next step."""
from __future__ import annotations

import json

from . import registry
from .db import DB
from .keys import KeyStore

EDITABLE = ("provider", "model", "fallback", "fallback_model", "month_usd")


def config(db: DB, slot: str) -> dict:
    base = next(b for b in registry.BRAIN_SLOTS if b["id"] == slot)
    saved = json.loads(db.get(f"brain:{slot}") or "{}")
    cfg = {k: base.get(k) for k in ("provider", "model", "fallback", "fallback_model")}
    cfg["month_usd"] = 20.0
    cfg.update({k: v for k, v in saved.items() if k in EDITABLE})
    return cfg


def save(db: DB, slot: str, values: dict) -> dict:
    if slot not in registry.BRAIN_IDS:
        raise ValueError("naməlum yuva")
    cfg = config(db, slot)
    for k in EDITABLE:
        if k not in values:
            continue
        v = values[k]
        if k in ("provider", "fallback"):
            if v in ("", None):
                v = None
            elif v not in registry.BRAIN_PROVIDERS:
                raise ValueError(f"naməlum provayder: {v}")
        elif k == "month_usd":
            v = float(v)
            if not 0 <= v <= 1000:
                raise ValueError("aylıq limit 0–1000 $ olmalıdır")
        else:
            v = (str(v).strip() or None) if v is not None else None
        cfg[k] = v
    if not cfg["provider"] or not cfg["model"]:
        raise ValueError("provayder və model boş ola bilməz")
    db.put(f"brain:{slot}", json.dumps(cfg))
    return cfg


def view(db: DB, keys: KeyStore) -> list[dict]:
    out = []
    for b in registry.BRAIN_SLOTS:
        cfg = config(db, b["id"])
        ks = keys.status(cfg["provider"])
        if not ks["saved"]:
            state = "açar yoxdur"
        elif ks["unreadable"]:
            state = "açarı yenidən daxil edin"
        elif ks["check"] and not ks["check"]["ok"]:
            state = "xəta"
        elif ks["check"] and ks["check"]["ok"]:
            state = "hazırdır"
        else:
            state = "yoxlanmayıb"
        out.append({**{k: b[k] for k in ("id", "name", "job", "may_not", "why")},
                    "requirements": [{"name": n, "weight": w} for n, w in b["requirements"]],
                    "config": cfg, "state": state, "in_use": False,
                    "default": {k: b[k] for k in ("provider", "model", "fallback", "fallback_model")}})
    return out
