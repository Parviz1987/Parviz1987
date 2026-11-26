"""Rəsmi rəqəmlər (official US release actuals, Block 9): the actual value of a US release straight from the agency, no
brain involved. BLS (CPI, payrolls, unemployment, hourly earnings, PPI) right at 8:30 New York; FRED for jobless claims,
PCE and GDP (FRED publishes within minutes to an hour). The figure is computed exactly as Forex Factory states its
estimate (m/m %, y/y %, change in thousands), stored with known_ts = the moment it was fetched, under the same id the
figure hunter uses — so the surprise method uses it and the two-brain web search is no longer needed for these.

A value is accepted only if its period is the one the release is about (e.g. October data for a November CPI release):
an agency that has not updated yet gives last month's figure, which must never be taken for this month's."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

# Forex Factory title (lower case, matched by regex) -> (source, series, transform, unit)
MAP = [
    (r"^core cpi m/m$", "bls", "CUSR0000SA0L1E", "mm"),
    (r"^cpi m/m$", "bls", "CUSR0000SA0", "mm"),
    (r"^cpi y/y$", "bls", "CUUR0000SA0", "yy"),
    (r"^core cpi y/y$", "bls", "CUUR0000SA0L1E", "yy"),
    (r"^non-farm employment change$", "bls", "CES0000000001", "chg"),
    (r"^unemployment rate$", "bls", "LNS14000000", "lvl"),
    (r"^average hourly earnings m/m$", "bls", "CES0500000003", "mm"),
    (r"^core ppi m/m$", "bls", "WPSFD49104", "mm"),
    (r"^ppi m/m$", "bls", "WPSFD4", "mm"),
    (r"^unemployment claims$", "fred", "ICSA", "k"),
    (r"^core pce price index m/m$", "fred", "PCEPILFE", "mm"),
    (r"^pce price index m/m$", "fred", "PCEPI", "mm"),
    (r"^(advance |prelim |final )?gdp q/q$", "fred", "A191RL1Q225SBEA", "lvl"),
    (r"^(advance |prelim |final )?gdp price index q/q$", "fred", "A191RI1Q225SBEA", "lvl"),   # the GDP deflator
]


def plan(title: str) -> tuple[str, str, str] | None:
    t = title.strip().lower()
    for rx, src, series, unit in MAP:
        if re.search(rx, t):
            return src, series, unit
    return None


def uid_of(title: str, ts: float) -> str:
    return "ff:" + hashlib.sha1(f"{title}|{ts}".encode()).hexdigest()[:16]


def expected_period(unit: str, series: str, release_ts: float) -> str:
    """The period a release is about, as YYYY-MM: monthly data -> the month before the release; claims -> the week
    (any date within 9 days before); GDP -> a quarter (checked loosely by the caller)."""
    d = datetime.fromtimestamp(release_ts, timezone.utc)
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return f"{y:04d}-{m:02d}"


def compute(unit: str, obs: list[tuple[str, float]]) -> tuple[str, float] | None:
    """obs: (YYYY-MM or YYYY-MM-DD, value), oldest first -> (period of the newest, the figure as FF states it)."""
    if not obs:
        return None
    per, v = obs[-1]
    if unit == "lvl":
        return per, round(v, 1)
    if unit == "k":
        return per, round(v / 1000, 0)
    if unit == "chg" and len(obs) >= 2:
        return per, round(v - obs[-2][1], 0)              # payrolls are in thousands already
    if unit == "mm" and len(obs) >= 2 and obs[-2][1]:
        return per, round((v / obs[-2][1] - 1) * 100, 1)
    if unit == "yy" and len(obs) >= 13 and obs[-13][1]:
        return per, round((v / obs[-13][1] - 1) * 100, 1)
    return None


def parse_bls(data: dict) -> dict[str, list[tuple[str, float]]]:
    """BLS API v2 -> series id -> [(YYYY-MM, value)] oldest first (monthly periods M01..M12 only)."""
    out = {}
    if not isinstance(data, dict) or data.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError(f"BLS: {(data or {}).get('message') if isinstance(data, dict) else 'cavab yoxdur'}")
    for s in data.get("Results", {}).get("series", []):
        rows = []
        for p in s.get("data", []):
            per = p.get("period", "")
            if not re.fullmatch(r"M(0[1-9]|1[0-2])", per):
                continue
            try:
                rows.append((f"{p['year']}-{per[1:]}", float(p["value"])))
            except (KeyError, ValueError):
                continue
        out[s.get("seriesID")] = sorted(rows)
    return out


def period_ok(unit: str, series: str, per: str, release_ts: float) -> bool:
    if series == "ICSA":
        d = datetime.strptime(per[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        return 0 <= release_ts - d <= 9 * 86400
    if series.startswith("A191"):
        d = datetime.strptime(per[:7] + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        return 30 * 86400 <= release_ts - d <= 200 * 86400       # the quarter just ended
    return per[:7] == expected_period(unit, series, release_ts)
