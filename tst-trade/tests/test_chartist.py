import asyncio
import json

from app import brains, brainjobs, llm
from app.db import DB
from app.keys import KeyStore


def test_chartist_reads_charts_and_stores_its_view(tmp_path, monkeypatch):
    db = DB(str(tmp_path / "t.db"))
    ks = KeyStore(db, "x" * 32)
    ks.set("anthropic", {"key": "sk-ant-1234"})
    now = 1_795_400_000.0
    rows = []
    for tf, step in (("1h", 3600), ("4h", 14400), ("1d", 86400)):
        for i in range(60):
            t = int(now // step * step) - step * (60 - i)
            rows.append(("XAU", tf, t, 4000 + i, 4002 + i, 3999 + i, 4001 + i))
    db.executemany("INSERT INTO candles(symbol, tf, t, o, h, l, c) VALUES(?,?,?,?,?,?,?)", rows)
    seen = {}

    async def fake_ask(provider, key, model, system, user, schema, max_tokens=2000):
        seen["user"] = user
        return {"metals": [{"symbol": "XAU", "trend": "yuxarı", "levels": "dəstək 9999", "pattern": "yox",
                            "p1h": 0.56, "p4h": 0.55, "p1d": 0.54, "why": "EMA-lar yuxarı düzülüb"}]}, 10, 10
    monkeypatch.setattr(llm, "ask", fake_ask)
    jobs = brainjobs.BrainJobs(db, ks, None)
    assert asyncio.run(jobs.chartist(now))
    facts = json.loads(seen["user"].split("\n", 1)[1])
    assert "1h" in facts["charts"]["XAU"] and facts["charts"]["XAU"]["1h"]["rsi14"] is not None
    v = db.execute("SELECT horizon, p FROM brain_views WHERE source='chartist' ORDER BY horizon").fetchall()
    assert [(r["horizon"], r["p"]) for r in v] == [("1d", 0.54), ("1h", 0.56), ("4h", 0.55)]
    assert json.loads(db.get("chartist:last"))["metals"][0]["levels"] == ""      # 9999 is not in the charts: dropped
