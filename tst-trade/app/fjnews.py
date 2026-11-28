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
_events: list = []        # the last few connects / closes with their time, kept in health (evidence for problems)
BUSY = {4029, 4030}       # «limit reached» / «replaced»: another connection holds the plan's one slot
STABLE_S = 120            # a connection that stayed open this long resets the retry wait


def _note(what: str) -> None:
    _events.append([round(time.time()), what[:80]])
    del _events[:-8]


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
    """Keeps one connection open (the Developer plan allows one). After a drop it waits 2 s, 4 s, 8 s … up to 5 min
    (30 min when the slot is busy or the key is refused); the wait starts again from 2 s only after a connection has
    stayed open STABLE_S — a connection that is opened and at once closed by the provider must not become a loop.
    A key saved anew in Admin is picked up within a minute."""
    wait = 2.0
    got = 0
    kinds: dict[str, int] = {}                # every message by type/event: «nothing came» ≠ «came but not read»
    while True:
        key = _key(keys)
        if not key:
            health(db, None, "açar yoxdur")
            await asyncio.sleep(60)
            continue
        opened = None
        try:
            async with _connect(key, ping_interval=30, open_timeout=20) as ws:
                opened = time.time()
                _live.update(key=key, ts=opened, got=got)
                _note("qoşuldu")
                health(db, True, "qoşuldu, başlıqlar gözlənilir", headlines=got, events=_events)
                last = time.time()
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 60)
                    except asyncio.TimeoutError:
                        raw = None
                    if raw is not None:
                        try:
                            m = json.loads(raw)
                            k = f"{m.get('type')}/{m.get('event')}" if isinstance(m, dict) else type(m).__name__
                            got += handle(db, m)
                            if k.startswith("hello/"):
                                _live["hello"] = str(raw)[:400]
                            elif k.startswith("error/"):          # 28.11: three came overnight, their text unknown
                                _live["last_error"] = [round(time.time()), str(raw)[:300]]
                        except (ValueError, TypeError, AttributeError):
                            k = "oxunmadı"
                        if k in kinds or len(kinds) < 12:
                            kinds[k] = kinds.get(k, 0) + 1
                    _live["got"] = got
                    if time.time() - last >= 60:
                        last = time.time()
                        health(db, True, f"işləyir: {got} başlıq, cəmi {sum(kinds.values())} mesaj (bu işə düşmədən bəri)",
                               headlines=got, kinds=kinds, hello=_live.get("hello"),
                               last_error=_live.get("last_error"), events=_events)
                        if _key(keys) != key:
                            break                               # new key in Admin: reconnect with it
            _live.clear()
            if _key(keys) != key:
                _note("yeni açar")
                continue                                        # the new key is tried at once
            _note("bağlandı")
            health(db, False, "axın bağlandı, yenidən qoşulur", headlines=got, events=_events)
        except asyncio.CancelledError:
            _live.clear()
            raise
        except Exception as e:
            _live.clear()
            code = _code(e)
            _note(f"bağlandı {code or type(e).__name__}")
            if opened and time.time() - opened >= STABLE_S:
                wait = 2.0                                      # it had worked for a while: a normal drop
            if code in BUSY:
                text = NO_RETRY.get(code) or "planın 1 qoşulma yeri başqa qoşulma ilə doludur"
                health(db, False, f"FinancialJuice: {text} ({code}) — {wait:.0f} s sonra yenidən", headlines=got,
                       events=_events)
                await _pause(keys, key, wait)
                wait = min(1800.0, wait * 2)
                continue
            if code in NO_RETRY:
                health(db, False, f"FinancialJuice: {NO_RETRY[code]} ({code})", events=_events)
                log.warning("financialjuice closed with %s: waiting 30 minutes or a new key", code)
                await _pause(keys, key, 1800)
                continue
            msg = str(e).replace(key, "***")
            health(db, False, f"{type(e).__name__}: {msg}"[:200], headlines=got, events=_events)
            log.warning("financialjuice: %s", msg[:200])
        else:
            if opened and time.time() - opened >= STABLE_S:
                wait = 2.0
        await _pause(keys, key, wait)
        wait = min(300.0, wait * 2)


def check(db: DB, creds: dict) -> tuple[bool | None, str]:
    """Admin's «Yoxla». Never opens a connection of its own: the plan allows one, and a second one pushes the live
    stream out (27.11 20:49: a check during the start led to «limit reached»). It reports what the live loop sees."""
    key = next((x for x in (creds or {}).values() if x), "")
    if _live.get("key") == key:
        return True, f"işləyir: canlı axın açıqdır, {_live.get('got', 0)} başlıq alınıb"
    try:
        h = json.loads(db.get(HEALTH) or "null") or {}
    except ValueError:
        h = {}
    if h.get("ok") is False:
        return False, str(h.get("msg") or "qoşulmur")
    return None, "açar saxlanıb; canlı axın bir dəqiqə ərzində qoşulur — sonra yenidən «Yoxla»"
