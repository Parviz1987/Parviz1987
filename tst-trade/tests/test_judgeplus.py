"""Hakimin gücləndirilməsi: more attempts deflate the Sharpe; near-duplicate attempts cannot lower the bar (floor);
PBO is high for noise and low for a real edge; Diebold–Mariano respects overlap; the e-value stays small for coins;
the Judge's self-check catches a peeking rule; a decaying approved method goes back to the shadow."""
import math
import random

from app import judgeplus as jp
from app.db import DB


def test_dsr_falls_with_more_attempts_and_duplicates_do_not_lower_the_bar():
    random.seed(1)
    rets = [random.gauss(0.0015, 0.01) for _ in range(500)]
    few, many = jp.dsr(rets, 5), jp.dsr(rets, 2000)
    assert few > many
    dup = jp.dsr(rets, 2000, [0.15] * 2000)                 # 2000 near-identical attempts: spread ~0
    assert dup <= jp.dsr(rets, 2000, [random.gauss(0, 0.05) for _ in range(2000)]) + 0.2
    assert dup < few


def test_pbo_noise_vs_real_edge():
    random.seed(2)
    noise = {f"m{i}": [random.gauss(0, 1) for _ in range(800)] for i in range(10)}
    real = {**{f"m{i}": [random.gauss(0, 1) for _ in range(800)] for i in range(9)},
            "good": [random.gauss(0.3, 1) for _ in range(800)]}
    assert jp.pbo(noise) > 0.25 and jp.pbo(real) < 0.10


def test_diebold_mariano_and_evalue():
    random.seed(3)
    ys = [int(random.random() < 0.5) for _ in range(600)]
    good = [0.65 if y else 0.35 for y in ys]
    good = [p if random.random() < 0.8 else 1 - p for p in good]
    mu, p = jp.diebold_mariano([(a - y) ** 2 for a, y in zip(good, ys)], [0.25] * 600, 1)
    assert mu < 0 and p < 0.05
    coins = [int(random.random() < 0.5) for _ in range(2000)]
    assert jp.evalue_hits(coins, 0.5) < jp.E_MIN
    assert jp.evalue_hits([1 if random.random() < 0.6 else 0 for _ in range(2000)], 0.5) > jp.E_MIN


def test_canary_catches_the_peek_and_random_rules_fail():
    db = DB(":memory:")
    random.seed(4)
    c, rows = 1800.0, []
    for i in range(900):
        c *= math.exp(random.gauss(0, 0.01))
        rows.append(("XAU", "1d", 1_600_000_000 + i * 86400, c, c, c, c))
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'history')", rows)
    out = jp.canary(db, seed=1)
    assert out["peek_caught"] and out["random_passed"] <= 1 and out["ok"]


def test_gates_need_every_check_and_the_card_says_why():
    random.seed(5)
    rets = [random.gauss(0, 0.01) for _ in range(400)]
    g = jp.gates(rets, [int(x > 0) for x in rets], [0.55] * 400, [int(x > 0) for x in rets], 0.5, 1, 1500, [], None)
    assert not g["ok"]
    card = jp.card({"status": "keçmədi", "gates": g, "net": -0.001}, 1500)
    assert card.startswith("Sübut kifayət deyil") and "xərc" in card
