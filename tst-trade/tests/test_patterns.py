"""All 12 kinds of technical analysis (owner 2026-11-25): detectors, the stop + target test, tick volume, replay."""
import re
from pathlib import Path

from app import candles, patterns, playbook, rules
from app.db import DB


def _c(t, o, h, l, c, v=None):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


def _series(closes, v=None):
    out, prev = [], closes[0]
    for k, x in enumerate(closes):
        o = prev
        out.append(_c(1_700_000_000 + 3600 * k, o, max(o, x) + 0.3, min(o, x) - 0.3, x, v))
        prev = x
    return out


def test_every_detector_rule_in_the_book_is_detected_in_code():
    from app import fundamental, newsblock
    code = (Path(rules.__file__).read_text() + Path(patterns.__file__).read_text() + Path(fundamental.__file__).read_text()
            + Path(newsblock.__file__).read_text())
    found = set(re.findall(r'"((?:TA|TH|PA|VOL|IM|FA|NW)-[A-Z0-9-]+)"', code))
    for r in playbook.RULES:
        if r["detector"]:
            assert r["id"] in found, r["id"]
    for rid in found:
        assert rid in playbook.BY_ID, rid                     # nothing detected that the book does not explain


def test_zigzag_alternates_and_keeps_the_extreme():
    cs = _series([10, 12, 11, 13, 9, 14, 8])
    zz = patterns.zigzag(cs, [1, 3, 5], [2, 4, 6])
    kinds = [k for _, k, _ in zz]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))
    zz2 = patterns.zigzag(cs, [1, 3], [])                      # two highs in a row: the higher one stays
    assert len(zz2) == 1 and zz2[0][0] == 3


def test_stop_target_counts_the_stop_first_and_waits_for_20_candles():
    flat = [_c(k, 100, 100.2, 99.8, 100) for k in range(30)]
    flat[3] = _c(3, 100, 103, 98, 100)                         # touches both: the stop counts (cautious)
    assert rules.stop_target(flat, 0, 1, 1.0) == (-1.0, 3)
    up = [_c(k, 100 + k, 100 + k + 0.5, 100 + k - 0.5, 100 + k) for k in range(30)]
    assert rules.stop_target(up, 0, 1, 1.0) == (2.0, 2)
    assert rules.stop_target(up, 15, 1, 1.0) is None          # 20 candles have not closed yet


def test_stochastic_and_obv():
    cs = _series([100 - k * 0.5 for k in range(20)] + [95, 96, 97, 98], v=10)
    k, d = patterns.stochastic(cs)
    assert k[19] is not None and k[19] < 20 and k[-1] > k[19]
    o = patterns.obv(cs)
    assert o[19] < 0 and o[-1] > o[19]
    assert patterns.obv(_series([1, 2, 3]))[2] is None         # no volume: no OBV


def test_double_top_fires_when_the_neckline_breaks():
    xs = [100 + k * 0.05 for k in range(230)]                  # long quiet rise for the indicators
    base = xs[-1]
    up = [base + 1.5 * k for k in range(1, 7)]                 # to the first top
    down = [up[-1] - 1.5 * k for k in range(1, 6)]             # to the neckline
    up2 = [down[-1] + 1.5 * k for k in range(1, 6)]            # the second, equal top
    fall = [up2[-1] - 1.5 * k for k in range(1, 12)]           # through the neckline
    cs = _series(xs + up + down + up2 + fall)
    ind = rules.Ind(cs)
    fired = []
    for i in range(240, len(cs)):
        fired += [r for r, d, _ in rules.detect(ind, i, tf="1h") if r == "TA-PAT-1" and d == -1]
    assert fired


def test_tick_volume_counts_price_changes_only():
    db = DB(":memory:")
    for p in (10.0, 10.0, 10.1, 10.1, 10.2):
        candles.add_tick(db, "XAU", 1_800_000_000, p)
    row = candles.get(db, "XAU", "1h")[-1]
    assert row["v"] == 3                                       # first tick + two changes
    candles.store_history(db, "XAG", "1h", [(1_800_000_000 // 3600 * 3600, 1, 1, 1, 1)])
    candles.add_tick(db, "XAG", 1_800_000_000, 2.0)            # a history candle finished live: never part-counted
    assert candles.get(db, "XAG", "1h")[-1]["v"] is None


def test_new_detector_version_replays_old_history_once(monkeypatch):
    db = DB(":memory:")
    rules.ensure(db)
    db.execute("INSERT INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note) "
               "VALUES('XAU','1h',1,'TA-TREND-1',1,1,1,'history','x')")
    db.put("rules:ver:XAU:1h", "old")
    seen = {}
    real = rules.detect

    def spy(ind, i, higher=None, pair=None, tf="1h"):
        seen.setdefault(tf, []).append(i)
        return real(ind, i, higher, pair, tf)
    monkeypatch.setattr(rules, "detect", spy)
    cs = _series([100 + (k % 50) * 0.3 for k in range(400)])
    monkeypatch.setattr(rules, "_load", lambda db_, sym, tf, now, limit=4500: cs if sym == "XAU" and tf == "1h" else [])
    rules.run(db, now=2_000_000_000)
    assert min(seen["1h"]) == 210                              # replayed from the start
    assert db.get("rules:ver:XAU:1h") == rules.RULES_VER
    seen.clear()
    rules.run(db, now=2_000_000_000)
    assert min(seen.get("1h", [10 ** 9])) >= 370               # then only the newest candles
    rec = rules.records(db)
    assert "rules" in rec


def test_volume_rules_are_tested_once_on_futures_volume():
    import random
    from app import futures
    db = DB(":memory:")
    db.script(futures.SCHEMA)
    random.seed(3)
    x, rows = 3000.0, []
    for k in range(60 * 24 * 40):                         # 40 days of one-minute bars with real volume
        o = x
        x *= 1 + random.gauss(0, 0.0006)
        rows.append(("XAU", 1_790_000_040 + 60 * k, o, max(o, x), min(o, x), x, random.randint(1, 50) *
                     (20 if k % 997 == 0 else 1)))
    db.executemany("INSERT INTO fut_candles(symbol, t, o, h, l, c, v) VALUES(?,?,?,?,?,?,?)", rows)
    n = rules.run_futures_volume(db)
    got = db.execute("SELECT DISTINCT rule, mode FROM rule_signals").fetchall()
    assert n > 0 and all(r["rule"].startswith("VOL-") and r["mode"] == "futures" for r in got)
    assert rules.run_futures_volume(db) == 0               # nothing new: nothing twice
    assert "VOL-" in "".join(rules.records(db)["rules"])


def test_daily_futures_refresh_needs_approval_and_respects_the_monthly_ceiling(monkeypatch):
    import asyncio
    import json
    from app import futures
    db = DB(":memory:")
    futures.ensure(db)
    db.execute("INSERT INTO fut_candles(symbol, t, o, h, l, c, v) VALUES('XAU', 1795305600, 1, 1, 1, 1, 1)")
    now = 1795305600 + 3 * 86400
    assert not asyncio.run(futures.daily_refresh(db, "k", now))["ok"]          # not approved: nothing bought
    db.put("futures:daily_approved", json.dumps({"by": "test"}))

    class R:
        def __init__(self, status, body):
            self.status_code, self._b, self.text = status, body, str(body)

        def json(self):
            return self._b
    calls = []

    class C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, auth=None):
            calls.append(url)
            if "get_dataset_range" in url:
                return R(200, {"start": "2010-06-06T00:00:00Z", "end": "2030-01-01T00:00:00Z"})
            if "get_cost" in url:
                return R(200, 0.9)
            return R(200, "ts_event,open,high,low,close,volume\n2026-11-23T00:00:00Z,1,2,0.5,1.5,10\n")
    monkeypatch.setattr(futures.httpx, "AsyncClient", C)
    res = asyncio.run(futures.daily_refresh(db, "k", now))
    assert res["ok"] and res["loaded"]["XAU"] == 1
    db.execute("INSERT INTO fut_candles(symbol, t, o, h, l, c, v) VALUES('XAU', ?, 1, 1, 1, 1, 1)", (now + 60,))
    res2 = asyncio.run(futures.daily_refresh(db, "k", now + 2 * 86400))        # 0.9 + 0.9 > 1.0 $: refused
    assert not res2["ok"] and "hədd" in res2["msg"]


def test_rules_analyst_votes_only_with_rules_that_had_an_edge_before_that_moment():
    db = DB(":memory:")
    rules.ensure(db)
    H = 3600
    rows = []
    for k in range(200):                    # TA-X was right 70 % of the time, TA-Y 30 %, on XAG (one hour each)
        t = 1_700_000_000 + k * H
        rows.append(("XAG", "1h", t, "TA-X", 1, 100.0, 101.0 if k % 10 < 7 else 99.0, "history", ""))
        rows.append(("XAG", "1h", t, "TA-Y", 1, 100.0, 101.0 if k % 10 < 3 else 99.0, "history", ""))
    t_now = 1_700_000_000 + 300 * H
    rows.append(("XAU", "1h", t_now - H, "TA-X", -1, 1.0, None, "live", ""))
    rows.append(("XAU", "1h", t_now - H, "TA-Y", 1, 1.0, None, "live", ""))
    db.executemany("INSERT INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note) "
                   "VALUES(?,?,?,?,?,?,?,?,?)", rows)
    lk = rules.Lookup(db)
    p, why = lk.views("XAU", t_now + rules.LAG, "1h")["qaydalar"]
    assert p < 0.5 and "TA-X" in why and "TA-Y" not in why          # only the rule with an edge votes
    p0, _ = lk.views("XAU", 1_700_000_000 + 5 * H, "1h")["qaydalar"]
    assert p0 == 0.5                                                   # early on nothing was known yet
    assert lk.weight("TA-X", "1h", 1_700_000_000 + 10 * H)[1] < 10     # outcomes count only after their candle
    from app import forecast
    assert "qaydalar" in forecast.methods_for("1h") and forecast.FAMILY["qaydalar"] in forecast.FAMILY_NAMES


def test_adx_measures_strength_and_every_rule_has_a_family():
    trend = _series([100 + k * 0.8 for k in range(120)])
    import math
    flat = _series([100 + 2 * math.sin(k / 2.0) for k in range(120)])
    a_t, p_t, m_t = rules.adx_series(trend)
    a_f, _, _ = rules.adx_series(flat)
    assert a_t[-1] > 25 and p_t[-1] > m_t[-1]
    assert a_f[-1] < 20
    assert rules.regime(15) == 0 and rules.regime(22) == 1 and rules.regime(40) == 2 and rules.regime(None) is None
    from app import fundamental, newsblock
    fams = {"Fundamental": fundamental.FAMILY, "Xəbər": newsblock.FAMILY}
    for r in playbook.RULES:
        if r["detector"]:
            assert r["id"] in (rules.RULE_FAMILY if r["area"] in playbook.TA_AREAS else fams[r["area"]]), r["id"]


def test_main_module_has_its_logger():
    from app import main
    assert main.log.name == "tst.main"            # the daily futures loop died on «name 'log' is not defined»


def test_ta_page_data_has_every_layer_and_the_rules_on_the_chart():
    from app import ta
    db = DB(":memory:")
    rows = []
    base = 1_800_000_000 // 3600 * 3600 - 400 * 3600
    x = 3000.0
    import math
    for k in range(400):
        o = x
        x = 3000 + 40 * math.sin(k / 15) + k * 0.2
        rows.append((base + k * 3600, o, max(o, x) + 1, min(o, x) - 1, x))
    candles.store_history(db, "XAU", "1h", rows)
    rules.ensure(db)
    db.execute("INSERT INTO rule_signals(metal, tf, t, rule, dir, price0, price1, mode, note) "
               "VALUES('XAU','1h',?, 'TA-SR-1', 1, 1, 1, 'live', 'test')", (rows[-2][0],))
    d = ta.build(db, "XAU", "1h", now=base + 400 * 3600 + 60)
    L = d["layers"]
    assert len(L["ichimoku"]["a"]) == len(d["candles"]) == len(L["adx"]["adx"]) == len(L["vol"])
    assert d["fired"] and d["fired"][0]["rule"] == "TA-SR-1"
    assert {r["id"] for r in d["book"]} == {r["id"] for r in playbook.RULES if r["detector"] and r["area"] in playbook.TA_AREAS}
    assert "vote" in d["now"] and d["now"]["regime"]


def test_daily_refresh_stops_at_databentos_history_end_and_bills_only_delivered(monkeypatch):
    import asyncio
    import json
    from app import futures
    db = DB(":memory:")
    futures.ensure(db)
    db.put("futures:daily_approved", json.dumps({"by": "test"}))
    last = 1795305600
    db.execute("INSERT INTO fut_candles(symbol, t, o, h, l, c, v) VALUES('XAU', ?, 1, 1, 1, 1, 1)", (last,))
    asked = []

    class R:
        def __init__(self, status, body):
            self.status_code, self._b, self.text = status, body, str(body)

        def json(self):
            return self._b

    class C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, auth=None):
            if "get_dataset_range" in url:
                return R(200, {"end": "2026-11-24T06:30:00Z"})
            asked.append(params.get("end"))
            if "get_cost" in url:
                return R(200, 0.04)
            return R(422, {"detail": "dataset_unavailable_range"})
    monkeypatch.setattr(futures.httpx, "AsyncClient", C)
    res = asyncio.run(futures.daily_refresh(db, "k", last + 3 * 86400))
    assert asked and all(e == "2026-11-24T06:00" for e in asked)                    # never past the history end
    assert not res["ok"] and res["cost_usd"] == 0 and res["month_spent_usd"] == 0      # refused: nothing billed


def test_every_method_belongs_to_exactly_one_block_and_families_are_the_blocks():
    from app import blocks, forecast
    for m in forecast.METHODS:
        if m in blocks.COMBINERS:
            continue
        owners = [b["id"] for b in blocks.BLOCKS if m in b["methods"]]
        assert len(owners) == 1, (m, owners)
        assert forecast.FAMILY[m] == owners[0], m
    assert set(forecast.FAMILY_NAMES) == {b["id"] for b in blocks.BLOCKS}
    db = DB(":memory:")
    from app.engine import Engine
    from app.keys import KeyStore
    Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    st = blocks.status(db, "XAU", "1h")
    assert {b["id"] for b in st["blocks"]} == {b["id"] for b in blocks.BLOCKS}
    assert "risk" in forecast.methods_for("1h") and "risk" not in forecast.methods_for("1w")


def test_central_bank_rule_uses_only_published_months():
    from app import fundamental
    from datetime import datetime, timezone
    db = DB(":memory:")
    db.script("CREATE TABLE IF NOT EXISTS cb_gold (country TEXT, period TEXT, oz REAL, PRIMARY KEY (country, period));")
    rows = []
    for k in range(48):
        y, m = 2022 + k // 12, k % 12 + 1
        buy = 3_000_000 if k >= 45 else 100_000          # the last three months: very strong buying
        for c in ("CHN", "IND", "TUR", "POL", "CZE"):
            rows.append((c, f"{y}-{m:02d}", 50_000_000 + k * 100_000 + (buy if k >= 45 else 0) * (k - 44)))
    db.executemany("INSERT INTO cb_gold VALUES(?,?,?)", rows)
    data = fundamental.Data(db)
    late = datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp()          # Dec 2025 public by mid-February 2026
    got = {r: d for r, d, _ in fundamental.detect(data, "XAU", late)}
    assert got.get("FA-CB-1") == 1
    early = datetime(2025, 12, 1, tzinfo=timezone.utc).timestamp()        # October (strong) is public only mid-December
    assert {r: d for r, d, _ in fundamental.detect(data, "XAU", early)}.get("FA-CB-1") != 1


def test_fundamental_page_data():
    from app import fundamental
    import math
    db = DB(":memory:")
    from app.engine import Engine
    from app.feeds import Feeds
    from app.keys import KeyStore
    Engine(db, KeyStore(db, "s" * 64), "demo", 15)
    Feeds(db, KeyStore(db, "s" * 64))
    base = 1_790_000_000 // 86400 * 86400
    rows = [(base + k * 86400, 3000 + k, 3010 + k, 2990 + k, 3000 + k + math.sin(k)) for k in range(300)
            if ((base + k * 86400) // 86400 + 3) % 7 < 5]
    candles.store_history(db, "XAU", "1d", rows)
    db.executemany("INSERT OR REPLACE INTO macro(series, d, v) VALUES(?,?,?)",
                   [("DFII10", (__import__("datetime").date(2026, 1, 1) + __import__("datetime").timedelta(days=k)).isoformat(), 2 - k * 0.01) for k in range(60)])
    d = fundamental.page(db, "XAU", now=base + 301 * 86400)
    assert d["candles"] and {f["id"] for f in d["factors"]} >= {"DFII10", "DGS2", "COT"}
    assert {r["id"] for r in d["book"]} >= {"FA-RY-1", "FA-CB-1"} and "vote" in d["now"]


def test_fed_odds_and_shanghai_premium_rules():
    from app import fundamental
    from datetime import date, timedelta, datetime, timezone
    db = DB(":memory:")
    from app.feeds import Feeds
    from app.keys import KeyStore
    Feeds(db, KeyStore(db, "s" * 64))
    db.script("CREATE TABLE IF NOT EXISTS fed_odds (ts REAL, ticker TEXT, title TEXT, prob REAL, close_ts REAL, "
              "PRIMARY KEY (ticker, ts));")
    meet = 1_900_000_000
    t0 = 1_800_000_000
    for day, cut in ((0, 0.2), (3, 0.6)):         # the cut odds rise from 20 % to 60 % in three days
        ts = t0 + day * 86400
        db.executemany("INSERT INTO fed_odds VALUES(?,?,?,?,?)", [
            (ts, "KXFEDDECISION-27JAN-C25", "", cut, meet), (ts, "KXFEDDECISION-27JAN-H0", "", 1 - cut, meet),
            (ts, "KXFEDDECISION-27JAN-H25", "", 0.0, meet)])
    data = fundamental.Data(db)
    got = {r: d for r, d, _ in fundamental.detect(data, "XAU", t0 + 3 * 86400 + 60)}
    assert got.get("FA-FED-2") == 1                 # more cuts expected: up for gold
    # Shanghai premium: 200 days at par, then a week at +2 %
    d0 = date(2026, 1, 1)
    rows_c, sge, cny = [], [], []
    for k in range(210):
        d = d0 + timedelta(days=k)
        ts = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        rows_c.append((ts, 3000, 3000, 3000, 3000))
        prem = 0.02 if k >= 203 else 0.0
        sge.append((d.isoformat(), 3000 * (1 + prem) * 7.0 / 31.1035, 1000.0))
        cny.append(("DEXCHUS", (d - timedelta(days=3)).isoformat(), 7.0))
    candles.store_history(db, "XAU", "1d", rows_c)
    db.script("CREATE TABLE IF NOT EXISTS sge_gold (d TEXT PRIMARY KEY, close REAL, volume_kg REAL);")
    db.executemany("INSERT INTO sge_gold VALUES(?,?,?)", sge)
    db.executemany("INSERT OR REPLACE INTO macro(series, d, v) VALUES(?,?,?)", cny)
    data = fundamental.Data(db)
    end = datetime(2026, 7, 31, tzinfo=timezone.utc).timestamp()
    got = {r: d for r, d, _ in fundamental.detect(data, "XAU", end)}
    assert got.get("FA-SGE-1") == 1


def test_gld_archive_parser_and_etf_rule():
    import io, zipfile
    from app import feeds, fundamental
    from datetime import date, timedelta, datetime, timezone
    rows_xml, strs = [], ["Date", "Tonnes of Gold"]
    d0 = date(2025, 1, 1)
    vals = []
    for k in range(320):
        vals.append(((d0 + timedelta(days=k)).strftime("%d-%b-%Y"), 900 + (0 if k < 310 else (k - 309) * 6)))
    for v, _ in vals:
        strs.append(v)
    rows_xml.append('<row r="1"><c r="A1" t="s"><v>0</v></c><c r="J1" t="s"><v>1</v></c></row>')
    for i, (d, t) in enumerate(vals):
        rows_xml.append(f'<row r="{i + 2}"><c r="A{i + 2}" t="s"><v>{i + 2}</v></c><c r="J{i + 2}"><v>{t}</v></c></row>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", "".join(f"<si><t>{s}</t></si>" for s in strs))
        z.writestr("xl/worksheets/sheet2.xml", "<sheetData>" + "".join(rows_xml) + "</sheetData>")
    got = feeds.parse_gld_xlsx(buf.getvalue())
    assert len(got) == 320 and got[0] == ("2025-01-01", 900.0)
    db = DB(":memory:")
    db.script("CREATE TABLE IF NOT EXISTS etf_gold (fund TEXT, d TEXT, tonnes REAL, PRIMARY KEY (fund, d));")
    db.executemany("INSERT INTO etf_gold VALUES('GLD',?,?)", got)
    data = fundamental.Data(db)
    end = datetime(2025, 11, 20, tzinfo=timezone.utc).timestamp()       # after the last ten days of strong inflows
    assert {r: d for r, d, _ in fundamental.detect(data, "XAU", end)}.get("FA-ETF-1") == 1


def test_news_page_data():
    from app import newsblock
    from app.brainjobs import BrainJobs
    from app.feeds import Feeds
    from app.keys import KeyStore
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    BrainJobs(db, ks, Feeds(db, ks))
    t = 1_800_000_000
    db.execute("INSERT INTO news (uid, source, url, title, ts) VALUES('n1','Reuters','u','Gold jumps on Middle East strike', ?)", (t - 600,))
    db.execute("INSERT INTO news_ai VALUES('n1', ?, 'geopolitics', 'XAU', 'up', 3, 'b')", (t - 500,))
    d = newsblock.page(db, "XAU", now=t)
    assert d["headlines"][0]["topic"] == "geosiyasət" and d["topics"]["geosiyasət"]["up"] == 1
    assert {r["id"] for r in d["book"]} == set(newsblock.FAMILY) and "vote" in d["now"]


def test_market_reporter_accepts_only_agreeing_figures_and_has_a_10_dollar_limit(monkeypatch):
    import asyncio
    from datetime import datetime, timezone
    from app import brains, fundamental, reporter
    from app.engine import Engine
    from app.keys import KeyStore
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    Engine(db, ks, "demo", 15).migrate()
    assert brains.config(db, "reporter")["month_usd"] == 10
    monkeypatch.setattr(ks, "first", lambda p: "k")
    answers = {"india_premium": [({"found": True, "value": -12, "period": "2026-11-20", "source_url": "https://a"}, "a"),
                                 ({"found": True, "value": -13, "period": "week ending 2026-11-20", "source_url": "https://b"}, "b")],
               "china_premium": [({"found": True, "value": 10, "period": "2026-11-20", "source_url": "https://a"}, "a"),
                                 ({"found": True, "value": 30, "period": "2026-11-20", "source_url": "https://b"}, "b")]}
    calls = []

    async def fake(db_, keys, slot, system, user, max_tokens=2000):
        assert slot == "reporter"
        topic = "india_premium" if "Indian gold dealers" in user else "china_premium"
        calls.append(topic)
        return answers[topic]
    monkeypatch.setattr(brains, "run_both", fake)
    fri = datetime(2026, 11, 20, 14, tzinfo=timezone.utc).timestamp()
    r = reporter.Reporter(db, ks)
    assert asyncio.run(r.tick(fri)) == 1                       # India agreed (−12 / −13); China did not (10 / 30)
    assert asyncio.run(r.tick(fri + 600)) == 0 and len(calls) == 2   # asked once a day
    got = reporter.accepted(db, "india_premium")
    assert got and got[0][1] == "2026-11-20" and got[0][2] == -12.5
    assert reporter.accepted(db, "china_premium") == []
    # a second, higher week: the India rule fires
    db.execute("INSERT INTO market_reports VALUES('india_premium','2026-11-27',-2,'$/oz',?,'{}','{}',1,'x')", (fri + 7 * 86400,))
    data = fundamental.Data(db)
    assert {r_: d for r_, d, _ in fundamental.detect(data, "XAU", fri + 7 * 86400 + 60)}.get("FA-IND-1") == 1


def test_london_range_breakout_first_close_only():
    from datetime import datetime, timezone
    day = int(datetime(2026, 1, 14, tzinfo=timezone.utc).timestamp())     # winter: London = UTC
    cs = []
    for h in range(24):
        t = day + h * 3600
        if h < 7:
            cs.append(_c(t, 100, 101, 99, 100))                              # the Asian range 99-101
        elif h == 9:
            cs.append(_c(t, 100.5, 103, 100.4, 102.5))                       # first close above: signal
        elif h == 10:
            cs.append(_c(t, 102.5, 104, 102, 103.5))                         # second close above: none
        else:
            cs.append(_c(t, 100, 100.6, 99.6, 100.2))
    got = [patterns.london_range(cs, i, 2.0) for i in range(24)]
    assert got[9] and got[9][0] == "TA-LDN-1" and got[9][1] == 1
    assert all(g is None for k, g in enumerate(got) if k != 9)
