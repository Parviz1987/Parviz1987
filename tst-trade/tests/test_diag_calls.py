from app import diag
from app.db import DB


def _fc(db, method, horizon, issued, p_up, hit=None, scored=None):
    db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, lo80, "
               "hi80, hit, scored_ts) VALUES('XAU', ?, ?, 'live', ?, ?, 1, ?, 1, 1, 1, 1, ?, ?)",
               (horizon, method, issued, issued + 3600, p_up, hit, scored))


def test_calls_say_who_said_up_and_who_said_down_and_who_was_right():
    # owner 2026-11-27: «which of our analysts said gold would rise?» needs each method's calls of the last hours,
    # not only its long-run hit rate
    db = DB(":memory:")
    now = 1_795_770_000
    _fc(db, "chartist", "1h", now - 7200, 0.35, hit=0, scored=now - 3600)       # said down, wrong
    _fc(db, "chartist", "1h", now - 3600, 0.40)                                  # said down, not scored yet
    _fc(db, "xeber", "1h", now - 7200, 0.62, hit=1, scored=now - 3600)          # said up, right
    _fc(db, "rw", "1h", now - 7200, 0.50)                                        # no view: not a call
    _fc(db, "xeber", "1h", now - 20 * 3600, 0.70)                                # outside the 12 hours
    out = diag._calls(db, now, hours=12)
    ch, xe = out["XAU"]["1h"]["chartist"], out["XAU"]["1h"]["xeber"]
    assert (ch["up"], ch["down"], ch["scored"], ch["right"]) == (0, 2, 1, 0)
    assert (xe["up"], xe["down"], xe["scored"], xe["right"]) == (1, 0, 1, 1)
    assert "rw" not in out["XAU"]["1h"]
    assert out["from"] == now - 12 * 3600
