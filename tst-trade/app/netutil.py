"""Outside downloads with a size cap and an overall time limit (audit C-078).

httpx's timeout covers each network step, not the whole answer: a source that trickles bytes, or sends a huge body,
could hold a collector (and memory) for long. `get` reads the answer in chunks, stops past `max_bytes` and gives up
after `deadline` seconds in all.
"""
from __future__ import annotations

import asyncio

import httpx

MAX_BYTES = 8 * 1024 * 1024
DEADLINE = 90.0


class TooLarge(httpx.HTTPError):
    def __init__(self, url, limit: int):
        super().__init__(f"answer from {httpx.URL(str(url)).host} larger than {limit} bytes")


async def get(client: httpx.AsyncClient, url, *, max_bytes: int = MAX_BYTES, deadline: float = DEADLINE,
              **kwargs) -> httpx.Response:
    """client.get(url, **kwargs) with the body capped at max_bytes and the whole exchange at deadline seconds."""
    if not hasattr(client, "stream"):          # a stand-in client of a test
        return await asyncio.wait_for(client.get(url, **kwargs), deadline)
    async def run() -> httpx.Response:
        async with client.stream("GET", url, **kwargs) as r:
            body = bytearray()
            async for chunk in r.aiter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    raise TooLarge(r.request.url, max_bytes)
            # aiter_bytes() already undid gzip / deflate / br: the rebuilt answer must not say it is still encoded,
            # or reading it decodes a second time ("incorrect header check", trading engine V2 audit 2026-10-31).
            headers = [(k, v) for k, v in r.headers.multi_items()
                       if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")]
            return httpx.Response(r.status_code, headers=headers, content=bytes(body), request=r.request,
                                  history=r.history)
    try:
        return await asyncio.wait_for(run(), deadline)
    except asyncio.TimeoutError as e:
        raise httpx.ReadTimeout(f"no complete answer within {deadline:.0f} s") from e
