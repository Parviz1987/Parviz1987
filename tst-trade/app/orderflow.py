"""Bazar axını (plan 27.11 step 11.1; owner: «bazarda böyük oyunçular alanda və ya satanda bilək»): every trade of the
COMEX gold, silver, platinum and palladium futures (front month), live from Databento (Standard plan, owner's
decision 27.11). Each trade carries its size and the side that started it (a buyer lifting the offer or a seller hitting
the bid), so per minute we know the real exchange volume and how much of it was buying, and a single very large trade
(a big player) is seen within seconds.

Kept small on purpose: per-minute sums (flow_min) and only the big trades (flow_big) are stored — a few MB a month.
A big trade is at least the 99.9th percentile of the last 5 000 trade sizes of that metal and never under BIG_MIN lots;
twice that raises an alarm (one per metal per 15 minutes). This is a new voice: it is measured by the Judge before it
may steer anything.

The client library (pandas, pyarrow, ~157 MB) is loaded only when the stream starts, and the stream starts only on a
server with MIN_MEM_MB of memory (the 1 GB server had 300-500 MB free; the resize to 2 GB is scheduled for 28.11)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque

from .db import DB

log = logging.getLogger("tst.orderflow")

SYMBOLS = {"GC.c.0": "XAU", "SI.c.0": "XAG", "PL.c.0": "XPT", "PA.c.0": "XPD"}
BIG_MIN = {"XAU": 20, "XAG": 10, "XPT": 10, "XPD": 5}      # lots: never call a smaller trade «big»
MIN_MEM_MB = 1500
HEALTH = "flow:health"
SCHEMA = """
CREATE TABLE IF NOT EXISTS flow_min (symbol TEXT NOT NULL, t INTEGER NOT NULL, trades INTEGER, vol INTEGER, buy INTEGER,
  sell INTEGER, big_buy INTEGER, big_sell INTEGER, PRIMARY KEY (symbol, t));
CREATE TABLE IF NOT EXISTS flow_big (symbol TEXT NOT NULL, ts REAL NOT NULL, price REAL, size INTEGER, side TEXT);
CREATE INDEX IF NOT EXISTS flow_big_ts ON flow_big(ts);
"""
NAMES = {"XAU": "Qızıl", "XAG": "Gümüş", "XPT": "Platin", "XPD": "Palladium"}


def health(db: DB, ok: bool | None, msg: str, **extra) -> None:
    db.put(HEALTH, json.dumps({"ok": ok, "msg": msg[:200], "ts": time.time(), **extra}, ensure_ascii=False))


def mem_total_mb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


class Flow:
    """Per-minute sums and big trades from a stream of (metal, time, price, size, side)."""

    def __init__(self, db: DB):
        self.db = db
        db.script(SCHEMA)
        self.cur: dict[tuple[str, int], dict] = {}
        self.sizes: dict[str, deque] = {s: deque(maxlen=5000) for s in BIG_MIN}
        self.alarmed: dict[str, int] = {}
        self.count = 0

    def big_line(self, sym: str) -> float:
        xs = sorted(self.sizes[sym])
        p = xs[int(len(xs) * 0.999)] if len(xs) >= 1000 else 0
        return max(BIG_MIN[sym], p)

    def on_trade(self, sym: str, ts: float, price: float, size: int, buy: bool | None) -> dict | None:
        """Add one trade; returns the big trade (if it is one). buy None: the side is not known (not counted as
        buying or selling, only as volume)."""
        self.count += 1
        line = self.big_line(sym)
        self.sizes[sym].append(size)
        m = int(ts // 60) * 60
        for k in [k for k in self.cur if k[0] == sym and k[1] < m]:     # a minute that has ended is written once
            self._write(k)
        row = self.cur.setdefault((sym, m), {"trades": 0, "vol": 0, "buy": 0, "sell": 0, "big_buy": 0, "big_sell": 0})
        row["trades"] += 1
        row["vol"] += size
        if buy is True:
            row["buy"] += size
        elif buy is False:
            row["sell"] += size
        if size < line or buy is None:
            return None
        row["big_buy" if buy else "big_sell"] += 1
        self.db.execute("INSERT INTO flow_big(symbol, ts, price, size, side) VALUES(?,?,?,?,?)",
                        (sym, ts, price, size, "buy" if buy else "sell"))
        return {"symbol": sym, "ts": ts, "price": price, "size": size, "buy": buy, "line": line}

    def _write(self, k: tuple[str, int]) -> None:
        r = self.cur.pop(k)
        self.db.execute("INSERT OR REPLACE INTO flow_min(symbol, t, trades, vol, buy, sell, big_buy, big_sell) "
                        "VALUES(?,?,?,?,?,?,?,?)", (k[0], k[1], r["trades"], r["vol"], r["buy"], r["sell"],
                                                     r["big_buy"], r["big_sell"]))

    def alarm(self, big: dict) -> bool:
        """A trade at least twice the big line raises an alarm: at most one per metal per 15 minutes."""
        if big["size"] < 2 * big["line"]:
            return False
        q = int(big["ts"] // 900)
        if self.alarmed.get(big["symbol"]) == q:
            return False
        self.alarmed[big["symbol"]] = q
        from . import signals
        signals.ensure(self.db)
        side = "ALIŞ" if big["buy"] else "SATIŞ"
        return signals.emit(self.db, f"whale:{big['symbol']}:{q}", "whale",
                            f"{NAMES[big['symbol']]} fyuçersində böyük {side}: {big['size']} lot birdən "
                            f"(adi böyük əməliyyat ≥ {big['line']:.0f} lot), qiymət {big['price']:.2f}",
                            3 if big["size"] >= 4 * big["line"] else 2, big["symbol"], big["ts"])


def view(db: DB, symbol: str, minutes: int = 60, now: float | None = None) -> dict:
    """For the panel line and the page: the last minutes' volume, the share started by buyers, the big trades."""
    now = time.time() if now is None else now
    db.script(SCHEMA)
    rows = [dict(r) for r in db.execute("SELECT t, trades, vol, buy, sell, big_buy, big_sell FROM flow_min WHERE symbol=? "
                                        "AND t > ? ORDER BY t", (symbol, now - minutes * 60)).fetchall()]
    big = [dict(r) for r in db.execute("SELECT ts, price, size, side FROM flow_big WHERE symbol=? AND ts > ? ORDER BY ts DESC "
                                       "LIMIT 20", (symbol, now - 24 * 3600)).fetchall()]
    vol, buy, sell = (sum(r[k] for r in rows) for k in ("vol", "buy", "sell"))
    return {"symbol": symbol, "minutes": rows, "big": big, "vol": vol,
            "buy_share": round(buy / (buy + sell), 3) if buy + sell else None,
            "health": json.loads(db.get(HEALTH) or "null")}


def _side(rec) -> bool | None:
    s = str(getattr(rec, "side", "N")).upper()
    if s.endswith("B") or s.endswith("BID"):
        return True
    if s.endswith("A") or s.endswith("ASK"):
        return False
    return None


async def run(db: DB, keys) -> None:
    """The live stream with its own reconnect: health says what is happening (no key / waiting for memory / working /
    the error Databento gave, e.g. a plan without live data)."""
    flow = Flow(db)
    wait = 60.0
    while True:
        try:
            creds = keys.get("databento") if keys is not None else None
            key = (creds or {}).get("key")
            if not key:
                health(db, None, "Databento açarı yoxdur")
                await asyncio.sleep(600)
                continue
            if mem_total_mb() < MIN_MEM_MB:
                health(db, None, f"server {mem_total_mb():.0f} MB: canlı axın 2 GB-dan sonra başlayacaq (şənbə 28.11)")
                await asyncio.sleep(1800)
                continue
            import databento                       # loaded only here (heavy)
            client = databento.Live(key=key)
            client.subscribe(dataset="GLBX.MDP3", schema="trades", stype_in="continuous", symbols=list(SYMBOLS))
            ids: dict[int, str] = {}
            health(db, True, "qoşuldu, əməliyyatlar gözlənilir")
            last_note = time.time()
            async for rec in client:
                if isinstance(rec, databento.SymbolMappingMsg):
                    sym = SYMBOLS.get(str(rec.stype_in_symbol))
                    if sym:
                        ids[rec.instrument_id] = sym
                elif isinstance(rec, databento.TradeMsg):
                    sym = ids.get(rec.instrument_id)
                    if not sym:
                        continue
                    big = flow.on_trade(sym, rec.ts_event / 1e9, float(rec.pretty_price), int(rec.size), _side(rec))
                    if big:
                        flow.alarm(big)
                elif isinstance(rec, databento.ErrorMsg):
                    health(db, False, f"Databento: {getattr(rec, 'err', rec)}")
                if time.time() - last_note > 60:
                    last_note = time.time()
                    health(db, True, f"işləyir: {flow.count} əməliyyat bu qoşulmada", trades=flow.count)
                    wait = 60.0
            health(db, False, "axın bağlandı, yenidən qoşulur")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            msg = str(e).replace(str((keys.get("databento") or {}).get("key") or "~~"), "***") if keys else str(e)
            health(db, False, f"{type(e).__name__}: {msg}"[:200])
            log.warning("orderflow: %s", msg[:200])
        await asyncio.sleep(wait)
        wait = min(600.0, wait * 2)
