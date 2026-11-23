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

from .base import PriceProvider, ProviderError, Quote

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


def quote_of(raw) -> dict | None:
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
    sym = SYMBOL.get(p.get("epic"))
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

    def __init__(self, creds: dict, on_quote: Callable[[Quote], None] | None = None, env: str | None = None):
        self.api_key = creds.get("api_key", "")
        self.login = creds.get("login", "")
        self.password = creds.get("password", "")
        # A key belongs to the demo or the real account; unknown: try demo first (no real money there), then real.
        self.envs = [env] if env in BASES else ["demo", "real"]
        self.env: str | None = env if env in BASES else None
        self.on_quote = on_quote
        self.latest: dict[str, Quote] = {}
        self.state = "connecting"
        self.error: str | None = None
        self.failed_logins = 0
        self.paused_until = 0.0
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
                async with connect(STREAM_URL) as ws:
                    await ws.send(_msg("marketData.subscribe", tokens, {"epics": list(EPIC.values())}))
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
                        q = quote_of(raw)
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
