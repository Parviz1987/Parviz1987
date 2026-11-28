"""Bazar axını (plan 27.11 step 11.1): per-minute sums, the buyers' share, big trades and their alarms."""
import json

from app import orderflow, pipeline, signals
from app.db import DB

T0 = 1_795_442_400.0                                  # Monday 10:00 New York


def test_minutes_sum_volume_and_the_side_that_started_each_trade():
    db = DB(":memory:")
    f = orderflow.Flow(db)
    f.on_trade("XAU", T0 + 1, 4000.0, 3, True)
    f.on_trade("XAU", T0 + 2, 4000.1, 1, False)
    f.on_trade("XAU", T0 + 3, 4000.1, 2, None)          # side unknown: volume only
    f.on_trade("XAU", T0 + 61, 4000.2, 1, True)          # next minute: the first is written
    r = db.execute("SELECT * FROM flow_min WHERE symbol='XAU' AND t=?", (int(T0),)).fetchone()
    assert (r["trades"], r["vol"], r["buy"], r["sell"]) == (3, 6, 3, 1)


def test_a_big_trade_is_kept_and_twice_the_line_alarms_once_per_quarter_hour():
    db = DB(":memory:")
    f = orderflow.Flow(db)
    for i in range(1200):                                # ordinary trades of 1-3 lots
        f.on_trade("XAU", T0 + i * 0.5, 4000.0, 1 + i % 3, i % 2 == 0)
    assert f.big_line("XAU") == 20                       # never under the floor
    assert f.on_trade("XAU", T0 + 700, 4001.0, 25, True)["size"] == 25          # big, but under twice the line
    assert not f.alarm({"symbol": "XAU", "ts": T0 + 700, "price": 4001.0, "size": 25, "buy": True, "line": 20})
    big = f.on_trade("XAU", T0 + 701, 4002.0, 90, False)
    signals.ensure(db)
    assert f.alarm(big)
    assert not f.alarm({**big, "ts": T0 + 702})          # the same quarter hour: no second alarm
    s = signals.recent(db)[0]
    assert s["kind"] == "whale" and "böyük SATIŞ" in s["text"] and s["strength"] == 3
    assert db.execute("SELECT COUNT(*) FROM flow_big").fetchone()[0] == 2


def test_view_gives_the_buyers_share_and_the_link_map_shows_the_stream_state():
    db = DB(":memory:")
    f = orderflow.Flow(db)
    now = T0 + 1800
    for i in range(10):
        f.on_trade("XAG", now - 600 + i * 60, 50.0, 4, i < 7)
    f.on_trade("XAG", now, 50.0, 1, True)                # closes the last full minute
    v = orderflow.view(db, "XAG", 60, now)
    assert v["vol"] == 40 and v["buy_share"] == 0.7
    orderflow.health(db, None, "server 961 MB: canlı axın 2 GB-dan sonra başlayacaq (şənbə 28.11)")
    rows = {r[0]: (r[2], r[3]) for r in pipeline._owner_steps(db, now)}
    assert rows["Databento canlı axını (böyük oyunçular, həqiqi həcm)"][0] == "owner"
    db.put("flow:health", json.dumps({"ok": False, "msg": "Databento: plan without live data", "ts": now}))
    rows = {r[0]: (r[2], r[3]) for r in pipeline._owner_steps(db, now)}
    assert rows["Databento canlı axını (böyük oyunçular, həqiqi həcm)"][0] == "bad"
