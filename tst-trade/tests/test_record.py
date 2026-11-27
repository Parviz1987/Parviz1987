from app import sieve
from app.db import DB


def _fc(db, sym, method, horizon, target, p_up, hit, basis="səbəb"):
    db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, lo80, "
               "hi80, basis, price1, outcome, hit, scored_ts) VALUES(?, ?, ?, 'live', ?, ?, 100, ?, 1, 1, 1, 1, ?, 101, 1, ?, ?)",
               (sym, horizon, method, target - 3600, target, p_up, basis, hit, target + 60))


def test_record_per_analyst_and_metal_shows_who_is_right_where():
    # owner 2026-11-27: «Əhməd qızılda düz deyir, gümüşdə səhv — Əhmədin qızılını gətirmək olar, gümüşünü yox»
    db = DB(":memory:")
    for k, hit in enumerate([1, 1, 1, 0, 1]):              # Əhməd in gold: 4 right of 5, the last one right
        _fc(db, "XAU", "chartist", "1h", 10_000 + k * 3600, 0.6, hit)
    for k, hit in enumerate([0, 0, 1, 0]):                 # Əhməd in silver: 1 of 4
        _fc(db, "XAG", "chartist", "1h", 10_000 + k * 3600, 0.6, hit)
    _fc(db, "XAU", "rw", "1h", 10_000, 0.5, None)          # no side: not a call
    out = sieve.record(db)
    gold = out["methods"]["chartist"]["XAU"]["1h"]
    silver = out["methods"]["chartist"]["XAG"]["1h"]
    assert (gold["n"], gold["right"]) == (5, 4) and gold["last"] == "11101"[::-1]     # newest first
    assert gold["streak"] == 1                             # the newest call came true: a run of 1
    assert (silver["n"], silver["right"]) == (4, 1) and silver["streak"] == -1
    assert out["methods"]["chartist"]["XAU"]["all"]["n"] == 5
    assert "rw" not in out["methods"]


def test_calls_can_be_asked_for_one_metal_and_horizon():
    db = DB(":memory:")
    _fc(db, "XAU", "chartist", "1h", 10_000, 0.6, 1, "qızıl")
    _fc(db, "XAG", "chartist", "1h", 10_000, 0.6, 0, "gümüş")
    _fc(db, "XAU", "chartist", "4h", 20_000, 0.4, 1, "4 saat")
    rows = sieve.calls(db, "chartist", "XAU", horizon="1h")
    assert [r["basis"] for r in rows] == ["qızıl"]


def test_record_page_and_api(tmp_path):
    from fastapi.testclient import TestClient
    from app import auth
    from tests.test_core import _app
    c = TestClient(_app(tmp_path))
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    c.cookies.set(auth.COOKIE, r.cookies[auth.COOKIE])
    page = c.get("/analitikler")
    assert page.status_code == 200 and "/static/nav.js" in page.text and "/static/analitikler.js" in page.text
    d = c.get("/api/record").json()
    assert {"methods", "names", "horizons"} <= set(d)
    assert c.get("/api/record?days=7").status_code == 200
    assert c.get("/api/record?days=5").status_code == 400
    assert c.get("/api/calls?method=chartist&symbol=XAU&horizon=1h").status_code == 200
    assert c.get("/api/calls?method=chartist&symbol=XAU&horizon=2h").status_code == 400
