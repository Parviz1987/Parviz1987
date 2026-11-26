"""Nəticə izi (owner 2026-11-26, plan step 2, layer 6): the numbers that decide what the owner sees — the full cost of
a forecast, target times, how the unified forecast and the Hedge weights learn, how a rule's record becomes a weight,
how the conductor combines voices, the market hours — computed on fixed, seeded data. If any of them changes, the
change touches results: it needs the owner's «okey» (tests/fingerprint.json is a protected file)."""
import hashlib
import json
import math
import random

DAY = 86400


def _seeded_db():
    from app.db import DB
    from app.judge import insert  # noqa: F401  (the schema)
    db = DB(":memory:")
    random.seed(7)
    t0 = 1_700_006_400
    rows = []
    for i in range(400):
        t = t0 + i * 3600
        p0 = 2000 + 20 * math.sin(i / 9)
        p1 = p0 * (1 + random.gauss(0, 0.002))
        for m, bias in (("tsmom", 0.04), ("qaydalar", -0.02), ("vaxt", 0.0), ("strateq", 0.06)):
            p = min(0.8, max(0.2, 0.5 + bias + random.gauss(0, 0.05)))
            hit = int((p > 0.5) == (p1 > p0))
            rows.append(("XAU", "1h", m, "history", t, t + 3600, p0, p, p0, p0, p0, p0, "", p1, t + 3700,
                         int(p1 > p0), hit, (p - (p1 > p0)) ** 2, 1, 1))
    db.executemany("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, "
                   "lo80, hi80, basis, price1, scored_ts, outcome, hit, brier, in50, in80) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return db


def compute() -> dict:
    from app import conductor, forecast, judge, learning, rules, unified
    from app.engine import market_open
    out = {}
    out["full_cost"] = {f"{s}:{h}": round(judge.full_cost(s, h), 8) for s in ("XAU", "XAG", "XPT", "XPD")
                        for h in ("1h", "4h", "1d", "1w")}
    out["target_time"] = {h: forecast.target_time(1_700_006_400, h) for h in ("15m", "1h", "4h", "1d", "1w")}
    db = _seeded_db()
    u = unified.simulate(db, "XAU", "1h")
    out["unified"] = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in u.items()
                      if k in ("n", "viewed", "hit_rate", "bss", "net_avg", "bias")}
    out["unified_w"] = {k: round(v, 6) for k, v in sorted(u["weights"].items())}
    out["hedge"] = learning.hedge(db, "XAU", "1h", now=1_700_006_400 + 401 * 3600)
    lk = rules.Lookup.__new__(rules.Lookup)
    lk.window = None
    lk.rec = {("R", "1d", None): ([i for i in range(1, 201)], [sum(1 for k in range(j + 1) if k % 3) for j in range(200)])}
    out["rule_weight"] = [round(x, 6) if isinstance(x, float) else x for x in lk.weight("R", "1d", 150)]
    random.seed(3)
    seq, sts = [], []
    for i in range(300):
        y = random.random() < 0.5
        seq.append({"t": i * DAY, "target": i * DAY + DAY - 60, "p0": 1.0, "p1": 1.01 if y else 0.99,
                    "v": {"A": random.choice((0.4, 0.6)), "B": 0.62 if y else 0.38}})
        sts.append(conductor.STATES[i % 4])
    c = conductor.simulate(seq, sts, 0.0)
    out["conductor"] = {a: c["arms"][a] for a in sorted(c["arms"])}
    out["market_open"] = [market_open(1_795_000_000 + k * 1800) for k in range(400)].count(True)
    return out


def digest(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()
