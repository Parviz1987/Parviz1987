"""The paid sources' one-month trial (plan 27.11 step 11.1) is fixed before the data: only cases after registration,
the trade starts after the label/alarm exists, the full cost is paid, under 30 cases is «az», never a «works»."""
from app import paidtrial
from app.db import DB

R = paidtrial.REGISTERED


def _db():
    db = DB(":memory:")
    db.script("""CREATE TABLE IF NOT EXISTS news_ai (uid TEXT PRIMARY KEY, ts REAL, event TEXT, metals TEXT,
                 direction TEXT, strength INTEGER, brain TEXT);
                 CREATE TABLE IF NOT EXISTS news (uid TEXT PRIMARY KEY, source TEXT, url TEXT, title TEXT, ts REAL,
                 metals TEXT, received_ts REAL);
                 CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, uid TEXT UNIQUE, ts REAL NOT NULL,
                 kind TEXT NOT NULL, metal TEXT, strength INTEGER, text TEXT, handled_ts REAL);""")
    return db


def _candles(db, t0, prices):
    for i, p in enumerate(prices):
        db.execute("INSERT OR REPLACE INTO candles(symbol, tf, t, o, h, l, c) VALUES('XAU','1m',?,?,?,?,?)",
                   (t0 + i * 60, p, p, p, p))


def test_few_cases_say_not_enough_and_old_cases_do_not_count():
    db = _db()
    base = R + 3600
    _candles(db, base, [4000 + i for i in range(20)])
    db.execute("INSERT INTO news_ai VALUES('fj:1', ?, 'x', 'XAU', 'up', 3, 'b')", (base - 30,))
    db.execute("INSERT INTO news_ai VALUES('fj:0', ?, 'x', 'XAU', 'up', 3, 'b')", (R - 60,))      # before registration
    db.execute("INSERT INTO news_ai VALUES('rss:9', ?, 'x', 'XAU', 'up', 3, 'b')", (base - 30,))  # another source
    out = paidtrial.evaluate(db, now=base + 3600)
    t1 = out["T1_financialjuice"]
    assert t1["n"] == 1 and t1["status"] == "az" and t1["hit_rate"] == 1.0


def test_entry_is_after_the_label_and_cost_is_paid():
    db = _db()
    base = R + 7200
    # the label comes at 10 s into a minute whose candle jumped: that jump must not be counted
    _candles(db, base, [3000] + [4000] * 20)
    db.execute("INSERT INTO news_ai VALUES('fj:2', ?, 'x', 'XAU,XAG', 'up', 2, 'b')", (base + 10,))
    t1 = paidtrial.evaluate(db, now=base + 3600)["T1_financialjuice"]
    assert t1["n"] == 1 and t1["hit_rate"] == 0.0 and t1["net_avg_pct"] < 0     # flat after entry: only the cost


def test_whale_alarms_with_a_real_edge_prove_and_without_it_do_not():
    db = _db()
    for k in range(40):
        t = R + 3600 + k * 3600
        _candles(db, t, [4000 + 2 * i for i in range(20)])                         # steady rise after each alarm
        db.execute("INSERT INTO signals(uid, ts, kind, metal, strength, text) VALUES(?,?,?,?,?,?)",
                   (f"whale:XAU:{k}", t - 20, "whale", "XAU", 3, "Qızıl fyuçersində böyük ALIŞ: 80 lot"))
    t2 = paidtrial.evaluate(db, now=R + 50 * 3600)["T2_databento"]
    assert t2["n"] == 40 and t2["alarms"] == 40 and t2["status"] == "sübut"
    db.execute("UPDATE signals SET text = 'Qızıl fyuçersində böyük SATIŞ: 80 lot'")
    assert paidtrial.evaluate(db, now=R + 50 * 3600)["T2_databento"]["status"] == "yox"
