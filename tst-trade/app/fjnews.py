"""FinancialJuice live headlines (plan 27.11 step 11.1; owner bought the Developer plan 27.11): macro, central banks,
geopolitics and commodities the moment they break, over the provider's WebSocket.

From the provider's own page (owner's screenshots 27.11): stream wss://stream.financialjuice.com/v1/stream, the key in
an «X-API-Key» header (servers) — never in the address, so it is not written in any log; every message is JSON
{type, event, data}; a headline is type «news», event «created», data {id, datePublished, title, labels, breaking,
level, link}. Close codes 4001 (bad key), 4003 (not allowed), 4030 (replaced by another connection): do not retry;
any other drop: reconnect.

Each headline goes into the same news table as every other source (with its arrival time, so its real delay is
measured), the Reader labels it like any other; a «breaking» headline of level 3 that touches gold, the dollar, the
Fed, US data or geopolitics raises a news alarm at once (one per headline)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime

from .db import DB

log = logging.getLogger("tst.fjnews")

STREAM = "wss://stream.financialjuice.com/v1/stream"
NO_RETRY = {4001: "açar səhvdir", 4003: "icazə yoxdur (plan bu kanalı vermir)",
            4030: "başqa qoşulma bu açarla açıldı (Developer planında 1 qoşulma)"}
HEALTH = "fj:health"
NOW_SQL = "(julianday('now') - 2440587.5) * 86400.0"
METAL_WORDS = {"XAU": r"\bgold\b|bullion", "XAG": r"\bsilver\b", "XPT": r"\bplatinum\b", "XPD": r"\bpalladium\b"}
RELEVANT = re.compile(r"\bgold|silver|platinum|palladium|metal|bullion|\busd\b|\bus\b|united states|\bfed\b|fomc|powell|"
                      r"treasur|inflation|\bcpi\b|\bpce\b|payroll|nfp|jobs|geopolit|war\b|missile|sanction|tariff|"
                      r"israel|iran|russia|ukraine|china|taiwan", re.I)


def health(db: DB, ok: bool | None, msg: str, **extra) -> None:
    db.put(HEALTH, json.dumps({"ok": ok, "msg": msg[:200], "ts": time.time(), **extra}, ensure_ascii=False))


def _ts(s: str | None) -> float:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return time.time()


def handle(db: DB, msg: dict) -> int:
    """One message from the stream. Returns 1 when a new headline was stored."""
    if not isinstance(msg, dict) or msg.get("type") != "news" or msg.get("event") not in ("created", None):
        return 0
    d = msg.get("data") or {}
    title = str(d.get("title") or "").strip()
    if not title or d.get("id") is None:
        return 0
    labels = [str(x) for x in (d.get("labels") or [])]
    text = (title + " " + " ".join(labels)).lower()
    metals = sorted(m for m, rx in METAL_WORDS.items() if re.search(rx, text))
    uid = f"fj:{d['id']}"
    link = str(d.get("link") or "")
    cur = db.execute("INSERT OR IGNORE INTO news(uid, source, url, title, ts, metals, received_ts) VALUES(?,?,?,?,?,?," +
                     NOW_SQL + ")", (uid, "FinancialJuice", link if link.startswith("https://") else "", title[:300],
                                     _ts(d.get("datePublished")), ",".join(metals)))
    if not cur.rowcount:
        return 0
    if d.get("breaking") and int(d.get("level") or 0) >= 3 and RELEVANT.search(text):
        from . import signals
        signals.ensure(db)
        signals.emit(db, "fjnews:" + str(d["id"]), "news", f"Təcili xəbər (FinancialJuice): {title}", 3,
                     ",".join(metals) or None)
    return 1


_live: dict = {}          # the open connection (single worker): key it uses, headlines so far — for «Yoxla»


def _key(keys) -> str | None:
    creds = keys.get("financialjuice") if keys is not None else None
    return next((v for v in (creds or {}).values() if v), None)


def _connect(key: str, **kw):
    import websockets
    try:
        return websockets.connect(STREAM, additional_headers={"X-API-Key": key}, **kw)
    except TypeError:                                           # websockets before 14
        return websockets.connect(STREAM, extra_headers={"X-API-Key": key}, **kw)


def _code(e: Exception):
    return getattr(getattr(e, "rcvd", None), "code", None) or getattr(e, "code", None)


async def _pause(keys, key: str, seconds: float) -> None:
    """Sleep, but stop early when the owner saves another key in Admin (it is tried at once)."""
    end = time.time() + seconds
    while time.time() < end:
        await asyncio.sleep(min(30.0, max(0.0, end - time.time())))
        if _key(keys) != key:
            return


async def run(db: DB, keys) -> None:
    """Keeps one connection open (the Developer plan allows one), reconnects after a drop, waits on a key problem;
    a key saved anew in Admin is picked up within a minute."""
    wait = 2.0
    got = 0
    replaced = 0
    while True:
        key = _key(keys)
        if not key:
            health(db, None, "açar yoxdur")
            await asyncio.sleep(60)
            continue
        try:
            async with _connect(key, ping_interval=30, open_timeout=20) as ws:
                _live.update(key=key, ts=time.time())
                health(db, True, "qoşuldu, başlıqlar gözlənilir", headlines=got)
                wait, replaced, last = 2.0, 0, time.time()
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 60)
                    except asyncio.TimeoutError:
                        raw = None
                    if raw is not None:
                        try:
                            got += handle(db, json.loads(raw))
                        except (ValueError, TypeError):
                            pass
                    _live["got"] = got
                    if time.time() - last >= 60:
                        last = time.time()
                        health(db, True, f"işləyir: {got} başlıq alınıb (son qoşulmadan bəri)", headlines=got)
                        if _key(keys) != key:
                            break                               # new key in Admin: reconnect with it
            _live.clear()
            if _key(keys) != key:
                continue                                        # the new key is tried at once
            health(db, False, "axın bağlandı, yenidən qoşulur", headlines=got)
        except asyncio.CancelledError:
            _live.clear()
            raise
        except Exception as e:
            _live.clear()
            code = _code(e)
            if code == 4030 and replaced < 3:                   # «Yoxla» or a short second connection: come back
                replaced += 1
                health(db, False, f"FinancialJuice: {NO_RETRY[4030]} — 60 saniyədən sonra yenidən", headlines=got)
                await _pause(keys, key, 60)
                continue
            if code in NO_RETRY:
                health(db, False, f"FinancialJuice: {NO_RETRY[code]} ({code})")
                log.warning("financialjuice closed with %s: waiting 30 minutes or a new key", code)
                await _pause(keys, key, 1800)
                replaced = 0
                continue
            msg = str(e).replace(key, "***")
            health(db, False, f"{type(e).__name__}: {msg}"[:200], headlines=got)
            log.warning("financialjuice: %s", msg[:200])
        await _pause(keys, key, wait)
        wait = min(300.0, wait * 2)


async def check(creds: dict) -> tuple[bool, str]:
    """Admin's «Yoxla». While the live connection is open with this key, its state is the answer (a second connection
    would push it out: the Developer plan allows one). Otherwise: open the stream once and close it."""
    key = next((x for x in (creds or {}).values() if x), "")
    if _live.get("key") == key:
        return True, f"işləyir: canlı axın açıqdır, {_live.get('got', 0)} başlıq alınıb"
    try:
        async with _connect(key, open_timeout=15) as ws:
            try:
                await asyncio.wait_for(ws.recv(), 3)
            except asyncio.TimeoutError:
                pass                                   # quiet minute: open and not refused is enough
        return True, "işləyir: açar qəbul olundu, canlı axın bir dəqiqəyə qoşulur"
    except Exception as e:
        code = _code(e)
        if code in NO_RETRY:
            return False, f"FinancialJuice: {NO_RETRY[code]} ({code})"
        return False, f"qoşulmaq alınmadı: {type(e).__name__}"
