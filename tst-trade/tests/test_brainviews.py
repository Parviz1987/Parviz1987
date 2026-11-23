from app import forecast
from app.brainjobs import BrainJobs
from app.brainviews import Lookup
from app.db import DB
from app.feeds import Feeds
from app.keys import KeyStore


def test_news_mood_and_strategist_lean_use_only_the_past():
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    BrainJobs(db, ks, Feeds(db, ks))
    t = 1_800_000_000
    for i, (d, s) in enumerate([("up", 2), ("up", 3), ("down", 1)]):
        db.execute("INSERT INTO news_ai VALUES(?,?,?,?,?,?,?)", (f"n{i}", t - 1800 + i * 60, "x", "XAU", d, s, "b"))
    db.execute("INSERT INTO news_ai VALUES('late', ?, 'x', 'XAU', 'down', 3, 'b')", (t + 30,))   # after the forecast
    db.execute("INSERT INTO brain_views VALUES(?, 'strateq', 'XAU', -1, 'b')", (t - 600,))
    v = Lookup(db).views("XAU", t, "4h")
    assert v["news"][0] > 0.5 and "+4" in v["news"][1]
    assert v["strateq"][0] == 0.4
    assert "strateq" not in Lookup(db).views("XAU", t, "15m")
    assert Lookup(db).views("XAG", t, "1h")["news"][0] == 0.5
    up = [{"o": 100 + i, "h": 100.5 + i, "l": 99.5 + i, "c": 100 + i} for i in range(60)]
    m = forecast.build(up, "4h", views=v)["methods"]
    assert m["news"]["p_up"] > 0.5 and m["strateq"]["p_up"] == 0.4
    assert "news" not in forecast.build(up, "1w")["methods"]
