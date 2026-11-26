"""Blokların yoxlanması və əlaqə xəritəsi (owner 2026-11-26, plan phase E and step B4): one sheet per block, built
from what the system already measures, so a weak or broken link is seen at once:
- inputs: its data sources' health (last check, ok or not);
- rules: how many of the block's rules fired in the last 24 hours and 7 days, and how many have a positive record;
- voice: on how many forecast moments its voice had a view (not 0.5) in the last 7 days;
- Judge: the best status of its voice on any desk; the conductor's evidence (does it differ between market states);
- value: how much the unified forecast loses without it (the block-value test, unified.ablation);
- links: which blocks it feeds and which feed it (from the block definitions).
A plain verdict per block: «sağlam», «zəif» (works but proves nothing), «qırıq» (an input or the voice is silent)."""
from __future__ import annotations

import json
import time

from .db import DB

PREFIX = {"ta": ("TA-", "TH-", "PA-", "VOL-", "IM-"), "fund": ("FA-",), "news": ("NW-",), "cross": ("CM-",),
          "time": ("TM-",), "brain": ()}
SOURCES = {"ta": [], "fund": ["fred", "cot", "official", "imf", "etf", "amfi"], "news": ["rss", "alpaca"],
           "cross": [], "time": ["forexfactory", "fmp"], "brain": []}
FEEDS = {"ta": ["vahid", "brain", "conductor"], "fund": ["vahid", "brain", "conductor"],
         "news": ["vahid", "brain", "conductor"], "cross": ["vahid", "brain", "conductor"],
         "time": ["vahid", "brain", "conductor"], "brain": ["vahid", "conductor"]}
ORDER = ("sübut", "namizəd", "xərc", "zəif", "az", "yox", "bazis")


def build(db: DB, now: float | None = None) -> dict:
    from . import rules
    from .blocks import BLOCKS
    rules.ensure(db)
    now = time.time() if now is None else now
    out = {"computed": now, "blocks": []}
    try:
        abl = json.loads(db.get("unified:ablation") or "{}").get("desks", {})
    except ValueError:
        abl = {}
    try:
        cond = json.loads(db.get("conductor:audit") or "{}").get("desks", {})
    except ValueError:
        cond = {}
    for b in BLOCKS:
        bid = b["id"]
        if bid not in PREFIX:
            continue
        sheet = {"id": bid, "name": b["name"], "voices": b.get("methods", []), "feeds": FEEDS.get(bid, []),
                 "fed_by": [x for x in ("ta", "fund", "news", "cross", "time") if bid == "brain"]}
        src = {}
        for sid in SOURCES.get(bid, []):
            h = json.loads(db.get(f"src:{sid}") or "{}")
            src[sid] = {"ok": h.get("ok"), "age_h": round((now - h["checked"]) / 3600, 1) if h.get("checked") else None,
                        "note": str(h.get("message") or "")[:80]}
        sheet["sources"] = src
        if PREFIX[bid]:
            like = " OR ".join("rule LIKE ?" for _ in PREFIX[bid])
            args = [p + "%" for p in PREFIX[bid]]
            day = db.execute(f"SELECT COUNT(*) n FROM rule_signals WHERE ({like}) AND t > ? AND mode='live'",
                             args + [now - 86400]).fetchone()["n"]
            week = db.execute(f"SELECT COUNT(*) n FROM rule_signals WHERE ({like}) AND t > ? AND mode='live'",
                              args + [now - 7 * 86400]).fetchone()["n"]
            sheet["rules"] = {"fired_24h": day, "fired_7d": week}
        views = {}
        for m in sheet["voices"]:
            r = db.execute("SELECT COUNT(*) n, SUM(p_up != 0.5) v FROM forecasts WHERE method=? AND mode='live' AND "
                           "issued_t > ?", (m, now - 7 * 86400)).fetchone()
            views[m] = {"moments": r["n"], "with_view": r["v"] or 0}
        sheet["views_7d"] = views
        best = None
        try:
            from .judge import stats
            for s in ("XAU",):
                for h in ("1h", "4h", "1d", "1w"):
                    for r in stats(db, s, h, ttl=600):
                        if r["method"] in sheet["voices"]:
                            st = r["status"]
                            if best is None or ORDER.index(st) < ORDER.index(best):
                                best = st
        except Exception:
            pass
        sheet["judge_best"] = best
        val = {}
        for h, d in abl.items():
            w = (d.get("without") or {}).get(bid)
            if w and w.get("bss_change") is not None:
                val[h] = w["bss_change"]               # positive: the forecast is WORSE without the block
        sheet["value_bss_drop"] = val
        diff = [v["voice"] for k, d in cond.items() for v in d.get("differ", []) if v["voice"] in sheet["voices"]]
        sheet["state_dependent"] = sorted(set(diff))
        wait_until = None
        if bid == "news":                # the news rules need a week of the Reader's labels before they may fire
            try:
                r = db.execute("SELECT MIN(ts) f, SUM(ts > ?) w, COUNT(*) n FROM news_ai", (now - 7 * 86400,)).fetchone()
                sheet["labels"] = {"first": r["f"], "last_7d": r["w"] or 0, "all": r["n"]}
                if r["n"] == 0:          # no labels at all yet: the Reader has not started
                    wait_until = now
            except Exception:
                sheet["labels"] = None
        silent_src = [k for k, v in src.items() if v["ok"] is False]
        any_view = sum(v["with_view"] for v in views.values())
        if wait_until and not silent_src:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            verdict = "gözləyir"
            why = "Oxuyucu hələ heç bir başlığı qiymətləndirməyib"
        elif silent_src or (views and any_view == 0):
            verdict = "qırıq"
            why = ("mənbə işləmir: " + ", ".join(silent_src)) if silent_src else "son 7 gündə səsin heç fikri olmayıb"
        elif best == "sübut":
            verdict, why = "sağlam", "Hakimin sübutu var"
        else:
            verdict = "zəif"
            why = "işləyir, amma xərcdən sonra sübut yoxdur"
        sheet["verdict"], sheet["why"] = verdict, why
        out["blocks"].append(sheet)
    db.put("blocks:audit", json.dumps(out, ensure_ascii=False))
    return out


def view(db: DB) -> dict | None:
    try:
        return json.loads(db.get("blocks:audit") or "null")
    except ValueError:
        return None
