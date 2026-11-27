from app import sieve
from app.db import DB


def _row(method, nh, hit, bar, status="yox", edge=0.0):
    return {"method": method, "nh": nh, "n": nh, "hit_rate": hit, "bar": bar, "status": status, "edge": edge}


def test_the_sieve_sorts_every_analyst_by_fixed_rules(monkeypatch):
    # owner 2026-11-27: a lab with too many tools; keep a record of who said what and filter: keep the ones that work,
    # list the rest for removal (removing stays the owner's decision)
    data = {
        ("XAU", "1h", "live"): [_row("good", 300, 0.60, 0.50, "sübut"), _row("bad", 400, 0.42, 0.50),
                                _row("flat", 500, 0.505, 0.50), _row("new", 30, 0.70, 0.50, "az"), _row("rw", 900, 0.5, 0.5, "bazis")],
        ("XAU", "1mo", "history"): [_row("flat", 2100, 0.53, 0.50)],    # 21 overlapping days: 100 independent cases
    }
    monkeypatch.setattr(sieve.judge, "stats", lambda db, s, h, m, ttl=0: data.get((s, h, m), []))
    out = {r["method"]: r for r in sieve.sieve(DB(":memory:"))["rows"]}
    assert out["good"]["verdict"] == "saxla"
    assert out["bad"]["verdict"] == "pis"                 # 8 points under chance on 400 calls: z < -2
    assert out["flat"]["verdict"] == "fərqsiz"            # many calls, no edge (overlap counted: 2100 / 21 = 100)
    assert out["new"]["verdict"] == "az"
    assert "rw" not in out                                # the no-direction baseline is not an analyst
    assert out["bad"]["worst"]["horizon"] == "1h" and out["bad"]["worst"]["n"] == 400


def test_the_journal_lists_each_call_with_its_basis_and_result():
    db = DB(":memory:")
    db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, lo80, "
               "hi80, basis, price1, outcome, hit, in80, scored_ts) VALUES('XAU', '1h', 'xeber', 'live', 100, 3700, 3600, "
               "0.40, 1, 1, 3590, 3610, 'Fed başlığı: aşağı', 3636, 1, 0, 0, 3760)")
    db.execute("INSERT INTO forecasts(symbol, horizon, method, mode, issued_t, target_t, price0, p_up, lo50, hi50, lo80, "
               "hi80, basis) VALUES('XAU', '1h', 'xeber', 'live', 3700, 7300, 3636, 0.5, 1, 1, 1, 1, 'fikir yoxdur')")
    rows = sieve.calls(db, "xeber")
    assert len(rows) == 1                                  # a «no view» forecast is not a call
    r = rows[0]
    assert r["said"] == "aşağı" and r["basis"] == "Fed başlığı: aşağı" and r["right"] is False
    assert abs(r["move_pct"] - (-1.0)) < 1e-9             # 3600 -> 3636 is +1 %, i.e. -1 % in the direction it said
