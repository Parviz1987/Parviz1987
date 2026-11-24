from app import judge
from app.providers.capital import parse_overnight


def test_full_cost_adds_slippage_and_nights():
    judge.set_swap({})
    spread = judge.COST["XAU"]
    assert judge.full_cost("XAU") == spread * 1.5                      # minutes: no night held
    assert abs(judge.full_cost("XAU", "1w") - (spread * 1.5 + 7 * judge.SWAP_GUESS)) < 1e-12
    assert judge.full_cost("XAU", "1h") < judge.full_cost("XAU", "1d") < judge.full_cost("XAU", "1mo")
    assert judge.cost_parts("XAU", "1d")["swap_source"] == "təxmini"


def test_broker_swap_replaces_estimate():
    judge.set_swap({"XAU": 0.0001})
    try:
        p = judge.cost_parts("XAU", "1d")
        assert p["swap_source"] == "broker" and abs(p["swap"] - 0.0001) < 1e-12
    finally:
        judge.set_swap({})


def test_parse_overnight():
    assert abs(parse_overnight({"instrument": {"overnightFee": {"longRate": -0.02, "shortRate": 0.005}}}) - 0.0001) < 1e-12
    assert parse_overnight({"instrument": {}}) is None
    assert parse_overnight(None) is None
