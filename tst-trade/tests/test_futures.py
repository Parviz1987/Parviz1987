from app import futures


def test_parse_csv_pretty():
    text = ("ts_event,rtype,publisher_id,instrument_id,open,high,low,close,volume,symbol\n"
            "2026-11-20T14:31:00.000000000Z,33,1,42,4012.1,4013.0,4011.5,4012.8,350,GC.v.0\n")
    rows = futures.parse_ohlcv_csv(text)
    assert rows[0][1:] == (4012.1, 4013.0, 4011.5, 4012.8, 350.0)
    assert rows[0][0] % 60 == 0


def test_window_is_two_years_ending_yesterday():
    s, e = futures._window(1795507725)
    assert e == "2026-11-23" and s.startswith("2024-11")
