from app import scoreboard
from app.db import DB

NY_NOON = 1_795_770_000 - (1_795_770_000 % 86400) + 17 * 3600      # some New York day, 12:00 (winter: UTC-5)


def _fc(db, sym, method, horizon, target, p_up, outcome, hit):
    db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, lo80, "
               "hi80, outcome, hit, scored_ts) VALUES(?, ?, ?, 'live', ?, ?, 1, ?, 1, 1, 1, 1, ?, ?, ?)",
               (sym, horizon, method, target - 3600, target, p_up, outcome, hit, target + 60))


def test_who_was_right_per_day_and_horizon_against_the_chance_of_that_day():
    db = DB(":memory:")
    t = NY_NOON
    # that day gold went up 3 times of 4 on the 1-hour desk (the market's own lean)
    for k, out in enumerate([1, 1, 1, 0]):
        _fc(db, "XAU", "up", "1h", t + k * 3600, 0.53, out, out)
    _fc(db, "XAU", "chartist", "1h", t, 0.60, 1, 1)                 # said up, right
    _fc(db, "XAU", "chartist", "1h", t + 3600, 0.40, 1, 0)          # said down, wrong
    _fc(db, "XAU", "xeber", "1h", t + 3 * 3600, 0.40, 0, 1)         # said down, right (the one down hour)
    _fc(db, "XAU", "rw", "1h", t, 0.50, 1, None)                    # no side: not counted
    d = scoreboard.board(db, "XAU", "day", now=t + 6 * 3600)      # 18:00 the same New York day
    ch = d["methods"]["chartist"]["1h"]
    assert (ch["n"], ch["right"]) == (2, 1)
    # the chance of being right by luck: up calls x 3/4 + down calls x 1/4
    assert abs(ch["chance"] - (0.75 + 0.25) / 2) < 1e-9
    assert d["methods"]["xeber"]["1h"]["right"] == 1
    assert "rw" not in d["methods"]
    assert d["market_up"]["1h"] == 0.75


def test_periods_and_all_metals():
    db = DB(":memory:")
    t = NY_NOON
    _fc(db, "XAU", "chartist", "1h", t - 3 * 86400, 0.6, 1, 1)      # three days ago
    _fc(db, "XAG", "chartist", "1h", t, 0.6, 0, 0)                  # today, silver
    now = t + 3600
    assert scoreboard.board(db, "ALL", "day", now=now)["methods"]["chartist"]["1h"]["n"] == 1
    assert scoreboard.board(db, "ALL", "7d", now=now)["methods"]["chartist"]["1h"]["n"] == 2
    assert scoreboard.board(db, "XAU", "7d", now=now)["methods"]["chartist"]["1h"]["n"] == 1
    assert scoreboard.board(db, "ALL", "yesterday", now=now)["methods"] == {}
