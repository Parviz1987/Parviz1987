"""The link map (plan 27.11, step 1.1): every voice, every source, the brains, the Judge's self-check, the owner's
steps and the age of the sheets — so a link that only says «ok» but does nothing is seen (owner 2026-11-27: «yalandan
işləyir deyən şeylər»)."""
import json

from app import blockaudit, pipeline
from app.brainjobs import BrainJobs
from app.db import DB
from app.engine import Engine
from app.feeds import Feeds
from app.keys import KeyStore

NOW = 1_795_442_400.0                       # Monday 23.11.2026 10:00 New York, market open


def _setup():
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    feeds = Feeds(db, ks)
    jobs = BrainJobs(db, ks, feeds)
    return db, ks, feeds, jobs, Engine(db, ks, "demo", 15, feeds, jobs)


def _fc(db, method, p_up, t, symbol="XAU", basis=""):
    db.execute("INSERT INTO forecasts(symbol, horizon, method, issued_t, target_t, price0, p_up, lo50, hi50, lo80, hi80, "
               "basis) VALUES(?, '1h', ?, ?, ?, 1, ?, 1, 1, 1, 1, ?)", (symbol, method, t, t + 3600, p_up, basis))


def _rows(db, ks, eng, feeds, jobs, now=NOW):
    return {r["stage"]: r for r in pipeline.check(db, ks, eng, feeds, jobs, now)}


def test_voices_counts_views_in_the_window_only():
    db = DB(":memory:")
    _fc(db, "qaydalar", 0.6, NOW - 3600)
    _fc(db, "qaydalar", 0.5, NOW - 7200)
    _fc(db, "qaydalar", 0.7, NOW - 10 * 86400)          # before the window
    v = blockaudit.voices(db, NOW - 7 * 86400)
    assert v["qaydalar"]["n"] == 2 and v["qaydalar"]["v"] == 1


def test_link_map_names_a_mute_voice_and_a_dead_one():
    db, ks, feeds, jobs, eng = _setup()
    from app import forecast
    for m in forecast.METHODS:                          # every voice speaks ...
        _fc(db, m, 0.6, NOW - 3600)
    db.execute("DELETE FROM forecasts WHERE method IN ('trendmix', 'tsmom')")
    _fc(db, "trendmix", 0.5, NOW - 3600, basis="mövsüm cədvəli yoxdur")   # ... but this one is always 0.5
    row = _rows(db, ks, eng, feeds, jobs)["Üsulların səsi (hər analitik)"]  # and «tsmom» issued nothing at all
    assert row["status"] == "bad"
    assert "susur" in row["msg"] and "fikri yoxdur" in row["msg"]
    assert "mövsüm cədvəli yoxdur" in row["msg"]
    assert "GARCH" not in row["msg"]                    # ranges only: no direction by design


def test_link_map_sees_a_source_that_answers_but_brings_nothing():
    db, ks, feeds, jobs, eng = _setup()
    feeds._health("alpaca", True, "0 başlıq (son 48 saat)", 0)
    feeds._health("rss", True, "259 başlıq; xəta: Google News: gümüş, platin: HTTP 429", 259)
    db.put("src:alpaca", json.dumps({**feeds.health("alpaca"), "checked": NOW - 60}))
    db.put("src:rss", json.dumps({**feeds.health("rss"), "checked": NOW - 60}))
    row = _rows(db, ks, eng, feeds, jobs)["Mənbələr (hər biri ayrıca)"]
    assert row["status"] == "warn"
    assert "heç nə gətirmir: alpaca" in row["msg"]
    assert "qismən: rss (Google News: gümüş, platin: HTTP 429)" in row["msg"]


def test_owner_steps_are_shown_as_waiting_never_as_working():
    db, ks, feeds, jobs, eng = _setup()
    db.put("backup:last", json.dumps({"ts": NOW - 3600, "ok": False, "msg": "R2 açarı saxlanmayıb"}))
    rows = _rows(db, ks, eng, feeds, jobs)
    assert rows["Kənar nəzarətçi (Healthchecks.io)"]["status"] == "owner"
    assert rows["İkinci ehtiyat nüsxə (Cloudflare R2)"]["status"] == "owner"
    assert "DigitalOcean" in rows["İkinci ehtiyat nüsxə (Cloudflare R2)"]["msg"]


def test_judge_self_check_failure_is_a_warning():
    db, ks, feeds, jobs, eng = _setup()
    db.put("judge:canary", json.dumps({"ts": NOW, "random_passed": 0, "random_n": 20, "peek30_hit": 0.64,
                                       "peek30_caught": False, "peek_caught": True, "ok": False}))
    row = _rows(db, ks, eng, feeds, jobs)["Hakimin öz yoxlaması (həftəlik)"]
    assert row["status"] == "warn" and "30 %" in row["msg"]


def test_an_old_sheet_is_named_with_its_age():
    db, ks, feeds, jobs, eng = _setup()
    db.put("blocks:audit", json.dumps({"computed": NOW - 17 * 3600, "blocks": []}))
    db.put("conductor:audit", json.dumps({"computed": NOW - 3600}))
    db.put("aci:shadow", json.dumps({"computed": NOW - 3600}))
    row = _rows(db, ks, eng, feeds, jobs)["Hesabat cədvəlləri (təzəlik)"]
    assert row["status"] == "warn" and "blokların yoxlaması (17 saat əvvəl)" in row["msg"]


def test_brains_with_failing_answers_are_named():
    db, ks, feeds, jobs, eng = _setup()
    from app import llmrouter
    llmrouter.Router(db)
    db.execute("CREATE TABLE IF NOT EXISTS brain_calls (ts REAL, slot TEXT, provider TEXT, model TEXT, ok INTEGER, "
               "usd REAL, error TEXT)")
    cols = [r[1] for r in db.execute("PRAGMA table_info(brain_calls)").fetchall()]
    for i in range(10):
        vals = {"ts": NOW - 600 - i * 300, "slot": "chartist", "provider": "openai", "model": "x", "ok": int(i < 3)}
        keys = [k for k in vals if k in cols]
        db.execute(f"INSERT INTO brain_calls({', '.join(keys)}) VALUES({', '.join('?' for _ in keys)})",
                   [vals[k] for k in keys])
    row = _rows(db, ks, eng, feeds, jobs)["Beyinlərin cavabı"]
    assert row["status"] == "warn" and "chartist 3/10" in row["msg"]


def test_a_failing_backup_is_never_green_and_a_job_saved_by_its_fallback_is_answered():
    db, ks, feeds, jobs, eng = _setup()
    db.put("backup:last", json.dumps({"ts": NOW - 3600, "ok": False, "msg": "ClientError 403"}))
    assert _rows(db, ks, eng, feeds, jobs)["İkinci ehtiyat nüsxə (Cloudflare R2)"]["status"] == "bad"
    db.execute("CREATE TABLE IF NOT EXISTS brain_calls (ts REAL, slot TEXT, provider TEXT, model TEXT, ok INTEGER, "
               "usd REAL, error TEXT)")
    for i in range(6):                     # each job: the primary fails, the fallback answers a few seconds later
        db.execute("INSERT INTO brain_calls(ts, slot, provider, model, ok) VALUES(?, 'reader', 'a', 'x', 0)",
                   (NOW - 1000 - i * 600,))
        db.execute("INSERT INTO brain_calls(ts, slot, provider, model, ok) VALUES(?, 'reader', 'b', 'y', 1)",
                   (NOW - 995 - i * 600,))
    assert _rows(db, ks, eng, feeds, jobs)["Beyinlərin cavabı"]["status"] == "ok"


def test_one_lucky_random_rule_is_not_a_warning_but_an_old_self_check_is():
    db, ks, feeds, jobs, eng = _setup()
    db.put("judge:canary", json.dumps({"ts": NOW - 3600, "random_passed": 1, "random_n": 20, "peek30_caught": True,
                                       "peek_caught": True, "ok": True}))
    assert _rows(db, ks, eng, feeds, jobs)["Hakimin öz yoxlaması (həftəlik)"]["status"] == "ok"
    db.put("judge:canary", json.dumps({"ts": NOW - 10 * 86400, "random_passed": 0, "random_n": 20,
                                       "peek30_caught": True, "peek_caught": True, "ok": True}))
    assert _rows(db, ks, eng, feeds, jobs)["Hakimin öz yoxlaması (həftəlik)"]["status"] == "warn"


def test_the_two_paid_feeds_wait_for_the_owner_until_connected():
    db, ks, feeds, jobs, eng = _setup()
    rows = _rows(db, ks, eng, feeds, jobs)
    assert rows["FinancialJuice (sürətli başlıqlar)"]["status"] == "owner"
    assert "Admin" in rows["FinancialJuice (sürətli başlıqlar)"]["msg"]
    assert rows["Databento canlı axını (böyük oyunçular, həqiqi həcm)"]["status"] == "owner"
    ks.set("financialjuice", {"key": "k"})
    from app import fjnews
    fjnews.health(db, False, "FinancialJuice: açar səhvdir (4001)")
    row = _rows(db, ks, eng, feeds, jobs)["FinancialJuice (sürətli başlıqlar)"]
    assert row["status"] == "bad" and "4001" in row["msg"]
