"""Laboratoriyalar (owner 28.11): each lab's rule on synthetic history — the timing (no look-ahead), the direction,
the verdict words, and that one lab's failure never hides the others."""
from datetime import datetime, timedelta, timezone

from app import labs
from app.db import DB


def _db_with_days(n=900, step=0.0):
    db = DB(":memory:")
    d0 = datetime(2023, 1, 2, tzinfo=timezone.utc)
    k, d = 0, d0
    while k < n:
        if d.weekday() < 5:
            p = 2000 * (1 + step) ** k
            db.execute("INSERT INTO candles(symbol, tf, t, o, h, l, c) VALUES('XAU','1d',?,?,?,?,?)",
                       (int(d.timestamp()), p, p, p, p))
            k += 1
        d += timedelta(days=1)
    return db


def test_the_verdict_words():
    few = labs.verdict([("2024-01-01", 0.01)] * 5, 0.0002, 20)
    assert few["status"] == "az"
    good = labs.verdict([(f"d{k:04d}", 0.01 if k % 10 < 8 else -0.005) for k in range(200)], 0.0002, 100)
    assert good["status"] == "sübut" and good["hit_rate"] == 0.8
    one_half = labs.verdict([(f"d{k:04d}", 0.01 if k >= 100 else -0.01) for k in range(200)], 0.0002, 100)
    assert one_half["status"] == "yox"


def test_the_data_lab_trades_after_the_release_in_the_hawkish_direction():
    db = _db_with_days(step=-0.001)                                  # gold falls every day
    db.script("CREATE TABLE ev_lib (id TEXT, kind TEXT, t REAL, period TEXT, value REAL, change REAL, base REAL, "
              "surprise REAL, cat TEXT, basis TEXT, usd_trend INTEGER, note TEXT)")
    for k in range(120):
        t = datetime(2023, 2, 1, 13, 30, tzinfo=timezone.utc) + timedelta(days=7 * k)
        while t.weekday() >= 5:
            t += timedelta(days=1)
        db.execute("INSERT INTO ev_lib(id, kind, t, cat, basis) VALUES(?, 'CPI', ?, 'yuxarı', 'x')", (str(k), t.timestamp()))
    out = labs.lab_data(db)
    assert out["n"] >= 100 and out["hit_rate"] == 1.0                    # stronger figure → gold down → right


def test_the_cot_lab_waits_for_publication_and_never_overlaps():
    db = _db_with_days(step=0.0005)                                  # gold rises
    db.script("CREATE TABLE cot (symbol TEXT, d TEXT, oi REAL, mm_long REAL, mm_short REAL, pm_long REAL, pm_short REAL)")
    d = datetime(2023, 1, 3)
    for k in range(190):
        net = 1000 if k < 170 else -5000                              # the last weeks fall to a 3-year low → «up»
        db.execute("INSERT INTO cot VALUES('XAU', ?, 0, ?, 0, 0, 0)", ((d + timedelta(weeks=k)).strftime("%Y-%m-%d"), net))
    out = labs.lab_cot(db)
    assert out["n"] >= 1 and out["hit_rate"] == 1.0
    assert out["first"] >= (d + timedelta(weeks=170, days=6)).strftime("%Y-%m-%d")      # never before publication
    assert out["n"] <= 5                                                   # 20 weeks of signals, 20-day trades, no overlap


def test_one_lab_failing_does_not_hide_the_others():
    out = labs.build(DB(":memory:"))
    assert [x["id"] for x in out["labs"]] == ["L1", "L2", "L3", "L4", "L5", "L6", "K1", "K2", "K3", "K4"]
    assert all(("gold" in x) or ("error" in x) for x in out["labs"])


def test_the_deep_cot_history_is_kept_apart_from_the_blocks_table(monkeypatch):
    import asyncio
    import httpx
    real = httpx.AsyncClient
    rows = [{"cftc_contract_market_code": "088691", "report_date_as_yyyy_mm_dd": f"20{10 + k:02d}-01-04T00:00:00.000",
             "open_interest_all": "1", "m_money_positions_long_all": "5", "m_money_positions_short_all": "2",
             "prod_merc_positions_long": "1", "prod_merc_positions_short": "1"} for k in range(30)]
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=rows))))
    db = DB(":memory:")
    assert asyncio.run(labs.refresh_cot(db)) == 30
    assert db.execute("SELECT COUNT(*) FROM cot_hist").fetchone()[0] == 30
    assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='cot'").fetchone()        # the block's table untouched


def test_a_start_before_the_price_history_is_no_trade():
    dates, closes = ["2020-01-02", "2020-01-03", "2020-01-06"] + [f"2020-02-{d:02d}" for d in range(3, 28)], [1.0] * 28
    assert labs._hold(dates, closes, "2015-06-01", 5) is None
    assert labs._hold(dates, closes, "2020-01-04", 5)[0] == "2020-01-06"          # a weekend start: the next day



def test_the_day_signal_labs_trade_from_the_next_close_without_overlap():
    dates = [f"2024-{1 + k // 28:02d}-{1 + k % 28:02d}" for k in range(60)]
    closes = [100.0 + k for k in range(60)]                          # gold rises steadily
    trades = labs._day_signals(dates, closes, lambda i: 1)            # a «long» signal every day
    assert trades[0][0] == dates[2] and len(trades) == 9             # from day 1's next close, every 6 days
    assert all(r > 0 for _, r in trades)


def test_the_corridor_lab_buys_the_lower_edge_and_skips_both_edges():
    db = DB(":memory:")                                   # the forecasts table comes with the schema
    t0 = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    for k in range(150):
        t = t0 + k * 86400
        lo, hi, close = (99, 101, 99.8)                      # day touches only the lower edge, closes back up
        if k % 10 == 0:
            lo, hi = 98, 102.5                               # touches both edges: no trade
        db.execute("INSERT INTO candles(symbol, tf, t, o, h, l, c) VALUES('XAU','1d',?,?,?,?,?)", (t, 100, hi, lo, close))
        db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, "
                   "lo80, hi80, price1) VALUES('XAU','1d','vahid','history',?,?,100,0.5,99.5,100.5,99,102,?)",
                   (t, t + 86400, close))
    out = labs.lab_corridor(db, "XAU", "1d", "80")
    assert out["n"] == 135 and out["hit_rate"] == 1.0          # bought at 99, closed at 99.8: 135 days, 15 skipped
    q = labs.corridor_quality(db)
    assert q["1d"]["cover80"] == 1.0 and q["1d"]["width80_pct"] == 3.0
