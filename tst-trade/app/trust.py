"""Etibar işığı (owner 2026-11-24: «the numbers confuse me — one simple result»): every analyst and the unified
forecast reduced to ONE light and ONE sentence, from the same numbers the Judge keeps.

- 🟢 etibarlı      the Judge's proof (money test after the full cost) — the only light that means «act»;
- 🟡 ümidverici    better than the simple model by a margin that is unlikely to be luck (z ≥ 1.5), not proven yet;
- ⚪ fərqi yoxdur   about as good as the simple model;
- 🔴 etibar yoxdur  worse than the simple model (z ≤ −1);
- ⏳ az            fewer than 10 cases: nothing to say yet.
The simple model is the STRONGEST free rival on the same cases, the same rule the Judge uses (owner 2026-11-25:
a brain that says «down» every time in a falling market looked 92 % right and lit yellow). For brains it is the best
of: «the move that already happened goes on», «the last day's direction goes on», and «always say what the market
did most often» (the majority share). For methods: the Judge's own bar. Cases close together are not independent
(one alarm covers four metals): the sample is the number of separate events when known, otherwise half the cases.
«Need» is roughly how many cases would make the same margin a proof."""
from __future__ import annotations

import math
import time

from .db import DB

NAMES = {"strateq": "Strateq", "brain2": "İkinci beyin", "debate": "Müzakirə", "chartist": "Qrafik analitiki"}
HN = {"15m": "15 dəq", "30m": "30 dəq", "1h": "1 saat", "4h": "4 saat", "1d": "1 gün", "1w": "1 həftə"}
LIGHT = {"green": "🟢 Etibarlı", "yellow": "🟡 Ümidverici", "white": "⚪ Fərqi yoxdur", "red": "🔴 Etibar yoxdur",
         "wait": "⏳ Az"}


def light(hit: float | None, n: int, base: float | None, proven: bool = False, events: int | None = None) -> dict:
    if proven:
        return {"light": "green", "z": None, "need": None}
    if hit is None or base is None or n < 10:
        return {"light": "wait", "z": None, "need": None}
    n_eff = max(1.0, min(n / 2, events) if events else n / 2)
    b = min(max(base, 0.05), 0.95)
    se = math.sqrt(b * (1 - b) / n_eff)
    diff = hit - base
    z = diff / se
    need = int((2.6 * math.sqrt(b * (1 - b)) / diff) ** 2 * n / n_eff) if diff > 0.01 else None
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


def brain_rival(r: dict) -> float | None:
    """The strongest free rival for a brain row (see the module note)."""
    opts = [r.get("baseline_hit"), r.get("trend_hit")]
    if r.get("went_up") is not None and r.get("n"):
        opts.append(max(r["went_up"], r["n"] - r["went_up"]) / r["n"])
    opts = [x for x in opts if x is not None]
    return max(opts) if opts else None


def build(db: DB) -> dict:
    from . import brainviews, judge
    items = []
    for r in brainviews.score(db, time.time()):
        name = f"{NAMES.get(r['brain'], r['brain'])}, {HN.get(r['horizon'], r['horizon'])}" + (
            ", həyəcandan sonra" if r["when"] == "həyəcan" else "")
        base = brain_rival(r)
        lt = light(r["hit_rate"], r["n"], base, events=r.get("events"))
        text = sentence(name, r["hit_rate"], r["n"], base, lt)
        if r.get("said_up") in (0, r["n"]) and r["n"] >= 10:      # one-sided: say so plainly
            text += (" Diqqət: hər dəfə eyni istiqaməti deyib (" + ("həmişə «düşəcək»" if r["said_up"] == 0 else
                     "həmişə «qalxacaq»") + "), dönüşü hələ heç tutmayıb.")
        items.append({"who": name, "kind": "beyin", **lt, "text": text})
    for h in ("15m", "1h", "4h", "1d", "1w"):
        st = {x["method"]: x for x in judge.stats(db, "XAU", h, "live", ttl=600)}
        v = st.get("vahid")
        if v:
            name = f"Vahid proqnoz, qızıl, {HN[h]}"
            proven = v["status"] == "sübut"
            if proven:                      # green only after the one-look final test (app/rigor.py)
                from .rigor import method_final
                proven = method_final(db, "XAU", h, "vahid").get("status") == "keçdi"
            lt = light(v["hit_rate"], v["nh"] or 0, v["bar"], proven)
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
