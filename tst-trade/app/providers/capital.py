"""Capital.com live quote stream (adapted from pj-trade-gold app/capstream.py and app/capitalcom.py).

The broker pushes every bid / offer change over a websocket, so the price arrives the moment it changes instead of
every 15-30 s. Price shown = (bid + offer) / 2 of the broker's GOLD, SILVER, PLATINUM, PALLADIUM markets (CFD quotes:
close to spot, not identical to it).

Login: POST /session with the API key in X-CAP-API-KEY and the login + the key's own password -> CST and
X-SECURITY-TOKEN; the stream wants both in every message, and a ping every few minutes keeps it. Capital.com blocks an
account after repeated failed logins, so a refused login waits 15, then 30, then 60 minutes before the next try."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable

import httpx

from .base import HistoryProvider, NotServed, PriceProvider, ProviderError, Quote

log = logging.getLogger("tst.capital")
BASES = {"real": "https://api-capital.backend-capital.com/api/v1",
         "demo": "https://demo-api-capital.backend-capital.com/api/v1"}
STREAM_URL = "wss://api-streaming-capital.backend-capital.com/connect"
EPIC = {"XAU": "GOLD", "XAG": "SILVER", "XPT": "PLATINUM", "XPD": "PALLADIUM"}
SYMBOL = {v: k for k, v in EPIC.items()}
PING_S = 300
RECV_S = 30.0
SILENT_S = 120.0            # no quote this long on an open stream (market open): reconnect
RETRY_S = 30.0
LOGIN_PAUSE = (900, 1800, 3600)


def quote_of(raw, symbols: dict | None = None) -> dict | None:
    try:
        j = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(j, dict) or j.get("destination") != "quote":
        return None
    p = j.get("payload") or {}
    try:
        bid, ofr = float(p["bid"]), float(p["ofr"])
    except (KeyError, TypeError, ValueError):
        return None
    sym = (symbols or SYMBOL).get(p.get("epic"))
    if sym is None or bid <= 0 or ofr <= 0:
        return None
    ts = p.get("timestamp")
    try:
        ts = float(ts) / (1000.0 if float(ts) > 1e12 else 1.0)
    except (TypeError, ValueError):
        ts = None
    return {"symbol": sym, "bid": bid, "ofr": ofr, "mid": round((bid + ofr) / 2, 5), "ts": ts}


def _msg(destination: str, tokens: dict, payload: dict | None = None) -> str:
    m = {"destination": destination, "correlationId": destination, "cst": tokens["CST"],
         "securityToken": tokens["X-SECURITY-TOKEN"]}
    if payload is not None:
        m["payload"] = payload
    return json.dumps(m)


class CapitalStream(PriceProvider):
    name = "capital"
    delayed = False

    def __init__(self, creds: dict, on_quote: Callable[[Quote], None] | None = None, env: str | None = None,
                 extra: dict[str, str] | None = None):
        self.api_key = creds.get("api_key", "")
        self.login = creds.get("login", "")
        self.password = creds.get("password", "")
        # A key belongs to the demo or the real account; unknown: try demo first (no real money there), then real.
        self.envs = [env] if env in BASES else ["demo", "real"]
        self.env: str | None = env if env in BASES else None
        self.on_quote = on_quote
        # metals plus the related markets found at the broker (code -> epic): one subscription for all
        self.epics = {**EPIC, **(extra or {})}
        self.symbols = {v: k for k, v in self.epics.items()}
        self.latest: dict[str, Quote] = {}
        self.state = "connecting"
        self.error: str | None = None
        self.failed_logins = 0
        self.paused_until = 0.0
        self.tokens: dict | None = None      # the stream's current session (history requests reuse it)
        self._task: asyncio.Task | None = None

    async def _session(self) -> dict:
        if time.time() < self.paused_until:
            raise ProviderError(f"Capital.com girişi fasilədədir ({int(self.paused_until - time.time())} san)")
        r = None
        async with httpx.AsyncClient(timeout=15.0) as c:
            for env in ([self.env] if self.env else self.envs):
                r = await c.post(f"{BASES[env]}/session", headers={"X-CAP-API-KEY": self.api_key},
                                 json={"identifier": self.login, "password": self.password, "encryptedPassword": False})
                if r.status_code == 200 and r.headers.get("CST"):
                    self.env = env
                    break
        cst, sec = r.headers.get("CST"), r.headers.get("X-SECURITY-TOKEN")
        if r.status_code != 200 or not cst or not sec:
            pause = LOGIN_PAUSE[min(self.failed_logins, len(LOGIN_PAUSE) - 1)]
            self.failed_logins += 1
            self.paused_until = time.time() + pause
            raise ProviderError(f"Capital.com girişi alınmadı (HTTP {r.status_code}); {pause // 60} dəq gözlənilir")
        self.failed_logins = 0
        return {"CST": cst, "X-SECURITY-TOKEN": sec}

    async def _run(self, connect) -> None:
        while True:
            try:
                self.state = "connecting"
                tokens = await self._session()
                self.tokens = tokens
                async with connect(STREAM_URL) as ws:
                    await ws.send(_msg("marketData.subscribe", tokens, {"epics": list(self.epics.values())}))
                    self.state, self.error = "live", None
                    last_ping = last_rx = time.monotonic()
                    while True:
                        if time.monotonic() - last_ping > PING_S:
                            await ws.send(_msg("ping", tokens))
                            last_ping = time.monotonic()
                        if time.monotonic() - last_rx > SILENT_S and _weekday_open(time.time()):
                            raise ProviderError("axın susdu, yenidən qoşulur")
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=RECV_S)
                        except asyncio.TimeoutError:
                            continue
                        q = quote_of(raw, self.symbols)
                        if q is None:
                            continue
                        last_rx = time.monotonic()
                        now = time.time()
                        quote = Quote(symbol=q["symbol"], price=q["mid"], source_ts=min(q["ts"] or now, now),
                                      bid=q["bid"], ask=q["ofr"], source_ts_missing=q["ts"] is None)
                        self.latest[q["symbol"]] = quote
                        if self.on_quote:
                            self.on_quote(quote)
            except asyncio.CancelledError:
                raise
            except Exception as e:   # any failure: wait and connect again; the panel shows the reason
                self.state, self.error = "error", str(e) or type(e).__name__
                log.warning("capital stream: %s", self.error)
                await asyncio.sleep(max(RETRY_S, self.paused_until - time.time()))

    def start(self, connect=None) -> None:
        if connect is None:
            import websockets
            connect = websockets.connect
        self._task = asyncio.create_task(self._run(connect))

    async def fetch(self, symbols: list[str]) -> tuple[list[Quote], dict[str, str]]:
        """The poll only reads what the stream already delivered (the stream itself stores every quote)."""
        if self._task is None:
            self.start()
        quotes = [self.latest[s] for s in symbols if s in self.latest]
        errors = {} if self.state == "live" else {"*": self.error or "Capital.com axını qoşulur"}
        return quotes, errors

    async def aclose(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass


def _weekday_open(ts: float) -> bool:
    from ..engine import market_open
    return market_open(ts)


# ---------- history ----------
RESOLUTION = {"1m": "MINUTE", "5m": "MINUTE_5", "15m": "MINUTE_15", "30m": "MINUTE_30", "1h": "HOUR", "4h": "HOUR_4", "1d": "DAY",
              "1w": "WEEK"}
MAX_ROWS = 1000             # the broker returns at most 1000 candles per request
PAGES_MAX = 10              # older pages walked back by date range (weekends make a page hold fewer candles)


def _mid(p: dict | None) -> float | None:
    if not isinstance(p, dict):
        return None
    bid, ask = p.get("bid"), p.get("ask")
    try:
        if bid is not None and ask is not None:
            return (float(bid) + float(ask)) / 2
        return float(bid if bid is not None else ask)
    except (TypeError, ValueError):
        return None


def parse_prices(data: object, tf: str) -> list[tuple[int, float, float, float, float]]:
    """GET /prices/{epic} -> (t, o, h, l, c) by the mid of bid and ask, oldest first.
    The broker starts its day and week on Sunday 22:00 UTC; those candles are moved to the trading day they belong to
    (Monday), so they line up with the panel's own UTC day and Monday-week candles."""
    from datetime import datetime, timezone
    from ..candles import bucket
    if not isinstance(data, dict) or not isinstance(data.get("prices"), list):
        raise ProviderError("Capital.com: gözlənilməyən tarixçə cavabı")
    out = {}
    for p in data["prices"]:
        raw = p.get("snapshotTimeUTC") or p.get("snapshotTime")
        o, h, l, c = (_mid(p.get(k)) for k in ("openPrice", "highPrice", "lowPrice", "closePrice"))
        if not raw or None in (o, h, l, c):
            continue
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "")).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
        t = bucket(ts + (2 * 3600 if tf in ("1d", "1w") else 0), tf)
        out[t] = (t, o, h, l, c)
    return [out[t] for t in sorted(out)]


class CapitalHistory(HistoryProvider):
    """OHLC history from the same broker as the live stream (all four metals, no extra plan needed)."""
    name = "capital"
    request_gap = 0.25

    def __init__(self, creds: dict, stream: "CapitalStream | None" = None, extra: dict[str, str] | None = None):
        self.stream = stream
        self.epics = {**EPIC, **(extra or {})}
        # Its own login helper: a refused history login must never pause the live stream's logins.
        self.login_helper = CapitalStream(creds, env=stream.env if stream is not None else None)
        self.tokens: dict | None = None
        self.client = httpx.AsyncClient(timeout=20.0)

    async def candles(self, symbol: str, tf: str, limit: int) -> list[tuple[int, float, float, float, float]]:
        if tf not in RESOLUTION or symbol not in self.epics:
            raise NotServed(f"{symbol} {tf}: Capital.com bu çərçivəni vermir")
        if self.tokens is None:
            live = self.stream.tokens if self.stream is not None else None
            self.tokens = live or await self.login_helper._session()
        base = BASES[self.login_helper.env or "real"]
        r = await self.client.get(f"{base}/prices/{self.epics[symbol]}",
                                  params={"resolution": RESOLUTION[tf], "max": min(limit, MAX_ROWS)},
                                  headers=self.tokens)
        if r.status_code in (400, 404):
            raise NotServed(f"HTTP {r.status_code}")
        if r.status_code == 401 and self.stream is not None:
            self.tokens = None     # the stream's session expired between requests: next request logs in afresh
            self.stream = None
        if r.status_code != 200:
            raise ProviderError(f"Capital.com tarixçə: HTTP {r.status_code}")
        rows = parse_prices(r.json(), tf)
        self.page_note = ""
        # More than one page: walk back by date range (the broker gives at most 1000 candles per request). A page
        # that fails ends the walk; what was loaded is kept.
        from datetime import datetime, timezone
        from ..candles import TF
        step = TF.get(tf, 60)
        cursor = rows[0][0] if rows else None        # walk back from here
        empty_ok = 2                                   # a page that is all weekend or holiday is stepped over
        for _ in range(PAGES_MAX):
            if len(rows) >= limit or cursor is None:
                break
            to = cursor - step
            frm = to - (MAX_ROWS - 1) * step            # never more than 1000 candle slots: a wider range is refused
            fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            if self.request_gap:
                await asyncio.sleep(self.request_gap)
            r = await self.client.get(f"{base}/prices/{self.epics[symbol]}",
                                      params={"resolution": RESOLUTION[tf], "max": MAX_ROWS, "from": fmt(frm),
                                              "to": fmt(to)}, headers=self.tokens)
            if r.status_code != 200:
                self.page_note = f"köhnə səhifə: HTTP {r.status_code} {r.text[:120]}"
                break
            older = [x for x in parse_prices(r.json(), tf) if x[0] < rows[0][0]]
            if not older:
                if empty_ok > 0:
                    empty_ok -= 1
                    cursor = frm
                    continue
                self.page_note = "köhnə səhifə boş gəldi"
                break
            rows = older + rows
            cursor = rows[0][0]
        return rows[-limit:]

    async def aclose(self) -> None:
        await self.client.aclose()
