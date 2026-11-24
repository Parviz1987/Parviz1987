"""COT, seasonality, jewellery calendar (ideas from the friend's project) and the Judge's scale (tərəzi)."""
from datetime import datetime, timezone

from app import forecast, judge, slowviews
from app.db import DB
from app.feeds import Feeds
from app.keys import KeyStore


def _db():
    db = DB(":memory:")
    Feeds(db, KeyStore(db, "s" * 64))          # creates the cot table
    return db


def ts(d):
    return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


def test_cot_contrarian_only_after_the_report_is_public():
    from datetime import date, timedelta
    db = _db()
    days = [(date(2021, 1, 5) + timedelta(weeks=i)).isoformat() for i in range(150)]   # Tuesdays
    db.executemany("INSERT OR REPLACE INTO cot(symbol, d, oi, mm_long, mm_short) VALUES(?,?,?,?,?)",
                   [("XAU", d, 1, 300 if i == 149 else 100 + (i * 7 % 10), 50) for i, d in enumerate(days)])
    lk = slowviews.Lookup(db)
    p, why = lk.views("XAU", ts(days[-1]) + 4 * 86400, "1mo")["cot"]
    assert p == 0.45 and "çox alıb" in why                     # the highest net in 3 years: crowded long
    # on Wednesday the newest report (the jump) is not public yet: the week before was ordinary
    assert lk.views("XAU", ts(days[-1]) + 86400, "1mo")["cot"][0] != 0.45
    assert lk.views("XAU", ts(days[-1]) + 4 * 86400, "1h") == {}


def test_season_needs_five_years_that_agree():
    db = _db()
    rows = []
    for y in range(2018, 2025):
        for d in range(1, 21):
            t = int(ts(f"{y}-01-{d:02d}"))
            rows.append(("XAU", "1d", t, 100 + d, 100 + d, 100 + d, 100 + d))   # every January rose
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c, origin) VALUES(?,?,?,?,?,?,?,'history')", rows)
    lk = slowviews.Lookup(db)
    assert lk.views("XAU", ts("2025-01-05"), "1mo")["season"][0] == 0.55
    assert lk.views("XAU", ts("2021-01-05"), "1mo")["season"][0] == 0.5       # only 3 Januaries before 2021


def test_jewel_window_before_diwali():
    assert slowviews.Lookup._jewel("XAU", ts("2026-10-25"))[0] == 0.55
    assert slowviews.Lookup._jewel("XPT", ts("2026-10-25"))[0] == 0.5
    assert slowviews.Lookup._jewel("XAU", ts("2026-07-01"))[0] == 0.5


def test_scale_weighs_only_analysts_above_the_bar():
    rows = [{"method": "momentum", "hit_rate": 0.60, "nh": 400, "bar": 0.5},
            {"method": "fib", "hit_rate": 0.49, "nh": 400, "bar": 0.5},
            {"method": "up", "hit_rate": 0.7, "nh": 400, "bar": 0.5},
            {"method": "news", "hit_rate": 0.9, "nh": 10, "bar": 0.5}]
    from app import learning
    w = learning.combine({"momentum": 1.5, "fib": 0.6, "news": 2.0}, rows, k=1)   # the scale's real weights
    assert set(w) == {"momentum"}
    v = forecast.weighted_view({"momentum": {"p_up": 0.6}, "fib": {"p_up": 0.3}}, w)
    assert v["p_up"] == 0.6 and "Momentum" in v["basis"]
    assert forecast.weighted_view({"momentum": {"p_up": 0.6}}, None)["p_up"] == 0.5
    assert {"cot", "season", "jewel"} <= set(forecast.methods_for("1mo"))
    assert "brain2" in forecast.methods_for("1h") and "cot" not in forecast.methods_for("1h")


def test_engine_weights_only_read_a_cache_filled_off_the_loop():
    from app.engine import Engine
    db = DB(":memory:")
    eng = Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    assert eng.weights("XAU", "1h") == {}            # nothing computed yet: no heavy query on the event loop
    eng.refresh_weights()
    assert eng.weights("XAU", "1h") == {}            # no record: nobody weighs anything
