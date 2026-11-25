"""Etibar işığı (owner 2026-11-24: «the numbers confuse me — one simple result»): every analyst and the unified
forecast reduced to ONE light and ONE sentence, from the same numbers the Judge keeps.

- 🟢 etibarlı      the Judge's proof (money test after the full cost) — the only light that means «act»;
- 🟡 ümidverici    better than the simple model by a margin that is unlikely to be luck (z ≥ 1.5), not proven yet;
- ⚪ fərqi yoxdur   about as good as the simple model;
- 🔴 etibar yoxdur  worse than the simple model (z ≤ −1);
- ⏳ az            fewer than 10 cases: nothing to say yet.
The simple model is the free rival on the same cases (for brains: «the move that already happened goes on»; for
methods: the no-skill level from the method's own long share). Cases close together are not independent (one
alarm covers four metals): the sample is halved before judging. «Need» is roughly how many cases would make the
same margin a proof."""
from __future__ import annotations

import math
import time

from .db import DB

NAMES = {"strateq": "Strateq", "brain2": "İkinci beyin", "debate": "Müzakirə", "chartist": "Qrafik analitiki"}
HN = {"15m": "15 dəq", "30m": "30 dəq", "1h": "1 saat", "4h": "4 saat", "1d": "1 gün", "1w": "1 həftə"}
LIGHT = {"green": "🟢 Etibarlı", "yellow": "🟡 Ümidverici", "white": "⚪ Fərqi yoxdur", "red": "🔴 Etibar yoxdur",
         "wait": "⏳ Az"}


def light(hit: float | None, n: int, base: float | None, proven: bool = False) -> dict:
    if proven:
        return {"light": "green", "z": None, "need": None}
    if hit is None or base is None or n < 10:
        return {"light": "wait", "z": None, "need": None}
    n_eff = max(1.0, n / 2)
    b = min(max(base, 0.05), 0.95)
    se = math.sqrt(b * (1 - b) / n_eff)
    diff = hit - base
    z = diff / se
    need = int((2.6 * math.sqrt(b * (1 - b)) / diff) ** 2 * 2) if diff > 0.01 else None
    if z >= 1.5:
        lt = "yellow"
    elif z <= -1.0:
        lt = "red"
    else:
        lt = "white"
    return {"light": lt, "z": round(z, 2), "need": need}


def sentence(name: str, hit: float | None, n: int, base: float | None, lt: dict) -> str:
    if lt["light"] == "wait":
        return f"{name}: hələ {n} hal var — danışmaq üçün tezdir."
    h, b = round(hit * 100), round(base * 100)
    if lt["light"] == "green":
        return f"{name}: Hakimin sübutu var (xərcdən sonra qazandırır)."
    if lt["light"] == "yellow":
        need = lt.get("need")
        if need and need > n:
            tail = f" Sübut üçün təxminən {need - n} hal da lazımdır."
        else:
            tail = " Say kifayət edir, amma Hakimin pul sınağını (tam xərcdən sonra, bütün analitiklər içində) hələ keçməyib."
        return f"{name}: {n} haldan {h} % düz, sadə model {b} % — yaxşıdır, amma hələ sübut deyil.{tail}"
    if lt["light"] == "red":
        return f"{name}: {h} % düz, sadə model {b} % — sadə modeldən pisdir."
    return f"{name}: {h} % düz, sadə model {b} % — fərq yoxdur."


def build(db: DB) -> dict:
    from . import brainviews, judge
    items = []
    for r in brainviews.score(db, time.time()):
        name = f"{NAMES.get(r['brain'], r['brain'])}, {HN.get(r['horizon'], r['horizon'])}" + (
            ", həyəcandan sonra" if r["when"] == "həyəcan" else "")
        lt = light(r["hit_rate"], r["n"], r.get("baseline_hit"))
        items.append({"who": name, "kind": "beyin", **lt, "text": sentence(name, r["hit_rate"], r["n"],
                                                                              r.get("baseline_hit"), lt)})
    for h in ("15m", "1h", "4h", "1d", "1w"):
        st = {x["method"]: x for x in judge.stats(db, "XAU", h, "live", ttl=600)}
        v = st.get("vahid")
        if v:
            name = f"Vahid proqnoz, qızıl, {HN[h]}"
            lt = light(v["hit_rate"], v["nh"] or 0, v["bar"], v["status"] == "sübut")
            items.append({"who": name, "kind": "vahid", **lt,
                          "text": sentence(name, v["hit_rate"], v["nh"] or 0, v["bar"], lt)})
    order = {"green": 0, "yellow": 1, "red": 2, "white": 3, "wait": 4}
    items.sort(key=lambda x: (order[x["light"]], -(x["z"] or 0)))
    greens = [x["who"] for x in items if x["light"] == "green"]
    yellows = [x["who"] for x in items if x["light"] == "yellow"]
    if greens:
        head = "Etibarlı proqnoz var: " + ", ".join(greens) + "."
    else:
        head = "Hazırda etibarlı (sübutlu) proqnoz yoxdur: AL / SAT göstərilmir."
    if yellows:
        head += " Ümidverici: " + ", ".join(yellows[:3]) + "."
    return {"ts": time.time(), "head": head, "items": items, "legend": LIGHT}
