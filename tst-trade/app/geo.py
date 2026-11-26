"""Ünvanın yeri (owner 2026-11-26: «from which country and city do they try to log in?»).

The country and city of an IP address from DB-IP's free «IP to City Lite» database (monthly, Creative Commons
Attribution 4.0: the page that shows a place links to db-ip.com). The file is downloaded by the server once a month
and read on the server only: no address is ever sent to anyone. Private and local addresses have no place."""
from __future__ import annotations

import gzip
import ipaddress
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

URL = "https://download.db-ip.com/free/dbip-city-lite-{ym}.mmdb.gz"
MAX_AGE = 35 * 86400
_READER = None
_READER_MTIME = 0.0


def path(db_path: str | Path) -> Path:
    return Path(db_path).parent / "geo" / "dbip-city-lite.mmdb"


def stale(db_path) -> bool:
    p = path(db_path)
    return not p.exists() or time.time() - p.stat().st_mtime > MAX_AGE


async def refresh(client, db_path, now: float | None = None) -> str:
    """Download this month's file (or last month's, early in a month) when ours is missing or older than 35 days."""
    if not stale(db_path):
        return "təzədir"
    now = time.time() if now is None else now
    d = datetime.fromtimestamp(now, timezone.utc)
    prev = (d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1)
    p = path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".gz.part")
    last = ""
    for y, m in ((d.year, d.month), prev):
        url = URL.format(ym=f"{y}-{m:02d}")
        async with client.stream("GET", url, timeout=120) as r:
            if r.status_code != 200:
                last = f"HTTP {r.status_code}"
                continue
            with open(tmp, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    f.write(chunk)
        import asyncio
        await asyncio.to_thread(_gunzip, tmp, p)
        return f"yükləndi: {y}-{m:02d}"
    raise ValueError(f"DB-IP faylı tapılmadı ({last})")


def _gunzip(src: Path, dst: Path) -> None:
    part = dst.with_suffix(".part")
    with gzip.open(src, "rb") as a, open(part, "wb") as b:
        shutil.copyfileobj(a, b, 1 << 20)
    os.replace(part, dst)                 # the reader never sees a half-written file
    src.unlink(missing_ok=True)


def place(ip: str, db_path) -> dict | None:
    """{"country": "Germany", "cc": "DE", "city": "Frankfurt am Main"} or None (no file, private address, unknown)."""
    global _READER, _READER_MTIME
    try:
        a = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return None
    if a.is_private or a.is_loopback or a.is_link_local or a.is_reserved:
        return None
    p = path(db_path)
    if not p.exists():
        return None
    try:
        import maxminddb
        mt = p.stat().st_mtime
        if _READER is None or mt != _READER_MTIME:
            _READER = maxminddb.open_database(str(p), maxminddb.MODE_MMAP)
            _READER_MTIME = mt
        r = _READER.get(str(a)) or {}
    except Exception:
        return None
    name = lambda x: ((x or {}).get("names") or {}).get("en")
    out = {"country": name(r.get("country")), "cc": (r.get("country") or {}).get("iso_code"), "city": name(r.get("city"))}
    return out if out["country"] or out["city"] else None


def label(pl: dict | None) -> str:
    if not pl:
        return "—"
    return ", ".join(x for x in (pl.get("city"), pl.get("country")) if x)
