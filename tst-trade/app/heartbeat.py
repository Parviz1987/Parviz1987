"""Kənar nəzarətçi — ürək döyüntüsü (owner 2026-11-26, plan step 1): the server and its important jobs tell an outside
service (Healthchecks.io) «I am alive» on time; when a signal does not come, that service writes to the owner's
Telegram itself, so the news arrives even when this server is dead (a dead server cannot say so).

One secret: a Healthchecks.io project API key (read-write), saved in Admin like the other keys (sealed in this server's
database, never in the repo, the browser or the chat). With it the checks below are created or updated on the
account automatically (name, period, grace, which channel); their ping addresses stay in this server's database.

Owner's decisions (2026-11-26): only four urgent cases go to Telegram at once (the panel, the price, the nightly backup,
a deploy rolled back); the rest go to the e-mail channel (the daily summary). A job that is skipped on purpose (the
market is closed) still sends a signal, with the text «atlandı», so a weekend never raises a false alarm. A signal
never makes a job wait: it is queued, sent in the background with a 10-second limit and at most 3 tries. Signal
texts carry no key, password or personal data."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .db import DB

log = logging.getLogger("tst.heartbeat")

API = "https://healthchecks.io/api/v3"
SLOT = "healthchecks"
URLS_KEY, LAST_KEY, SPEC_KEY = "hc:urls", "hc:last", "hc:spec"
TIMEOUT, TRIES = 10.0, 3
H = 3600
OK_EVERY = 300               # an «ok» of one check is sent at most every 5 minutes (fail/start always go)
BAD_IN_ROW = 3               # app-alive / price-feed: «fail» only after 3 bad samples in a row (15 minutes)
WARMUP = 600                 # no panel/price verdict in the first 10 minutes after a start (quotes still arriving)

# id, name shown on the account, period (s), grace (s), urgent (Telegram at once), what it means
CHECKS: list[dict] = [
    {"id": "app-alive", "timeout": 300, "grace": 600, "urgent": True,
     "desc": "Panel işləyir; bazar açıq ikən qiymət 10 dəqiqədən köhnə deyil."},
    {"id": "price-feed", "timeout": 300, "grace": 600, "urgent": True,
     "desc": "Açıq bazarda 4 metalın heç biri OFFLINE deyil."},
    {"id": "rule-blocks", "timeout": 2 * H, "grace": 2 * H, "urgent": False,
     "desc": "Şamlar və qayda blokları (TA, fundamental, bazarlar arası, vaxt) hesablanır."},
    {"id": "news-agents", "timeout": H, "grace": H, "urgent": False,
     "desc": "Xəbər mənbələri cavab verir (hamısı ardıcıl xəta verməyib)."},
    {"id": "ai-brains", "timeout": 2 * H, "grace": H, "urgent": False,
     "desc": "Ən azı bir AI beyni son dövrdə cavab verib."},
    {"id": "unified-forecast", "timeout": 6 * H, "grace": H, "urgent": False,
     "desc": "Vahid proqnozun öz-özünü sınağı yenilənib."},
    {"id": "judge-scoring", "timeout": H, "grace": 2 * H, "urgent": False,
     "desc": "Hakim vaxtı çatan proqnozları yoxlayır."},
    {"id": "learning-nightly", "timeout": 24 * H, "grace": 3 * H, "urgent": False,
     "desc": "Gecə öyrənməsi (çəkilər, kalibrləmə, dirijor) işləyib."},
    {"id": "hypothesis-weekly", "timeout": 7 * 24 * H, "grace": 24 * H, "urgent": False,
     "desc": "Həftəlik hipotez agenti işə düşüb."},
    {"id": "duty-check", "timeout": 3 * H, "grace": H, "urgent": False,
     "desc": "3 saatlıq Claude növbətçisi diaqnostikanı oxuyub."},
    {"id": "backup-nightly", "timeout": 24 * H, "grace": 2 * H, "urgent": True,
     "desc": "Gecəlik ehtiyat nüsxə alınıb və yoxlamadan keçib."},
    {"id": "deploy", "timeout": 30 * 24 * H, "grace": H, "urgent": True,
     "desc": "Yeni versiya açıldı; geri qaytarılsa dərhal xəbər gəlir."},
]
IDS = {c["id"] for c in CHECKS}


class Heart:
    def __init__(self, db: DB, keys):
        self.db, self.keys = db, keys
        self.queue: list[tuple[str, str, str]] = []
        self._lock = threading.Lock()         # jobs in worker threads (the nightly backup) beat too
        self._ok_t: dict[str, float] = {}
        self.started = time.time()
        self.bad: dict[str, int] = {}

    # ---------- the jobs call this ----------
    def beat(self, check: str, state: str = "ok", msg: str = "") -> None:
        """Queue a signal: state «ok», «start» or «fail». Never blocks, never raises."""
        try:
            if check not in IDS or state not in ("ok", "start", "fail"):
                return
            now = time.time()
            with self._lock:
                if state == "ok":
                    if now - self._ok_t.get(check, 0.0) < OK_EVERY:
                        return                 # a busy job (scoring every 15 s) does not flood the service
                    self._ok_t[check] = now
                else:
                    self._ok_t.pop(check, None)
                self.queue = [q for q in self.queue if q[0] != check or q[1] == "start"][-50:]
                self.queue.append((check, state, str(msg)[:500]))
        except Exception:                      # a signal must never break the job that sends it
            pass

    def skip(self, check: str, why: str) -> None:
        self.beat(check, "ok", f"atlandı: {why}")

    # ---------- account set-up ----------
    def _key(self) -> str | None:
        return self.keys.first(SLOT) if self.keys is not None else None

    async def setup(self, client: httpx.AsyncClient) -> dict:
        """Create or update the checks on the account (unique by name) and keep their ping addresses here. Runs when the
        key is new or the list above changed."""
        key = self._key()
        if not key:
            return {"ok": False, "note": "Healthchecks.io açarı saxlanmayıb"}
        hdr = {"X-Api-Key": key}
        r = await client.get(f"{API}/channels/", headers=hdr, timeout=TIMEOUT)
        if r.status_code in (401, 403):
            return {"ok": False, "note": "açar qəbul olunmadı: layihənin yazma icazəli API açarı lazımdır"}
        r.raise_for_status()
        chans = r.json().get("channels", [])
        tg = [c["id"] for c in chans if c.get("kind") == "telegram"]
        mail = [c["id"] for c in chans if c.get("kind") == "email"]
        # the owner may add Telegram after saving the key: the channels are part of what is checked every hour
        spec = hashlib.sha256((json.dumps(CHECKS, sort_keys=True) + key + ",".join(sorted(tg + mail)))
                              .encode()).hexdigest()
        if self.db.get(SPEC_KEY) == spec and self.db.get(URLS_KEY):
            return {"ok": True, "note": f"hazırdır; Telegram kanalı: {'var' if tg else 'YOXDUR'}"}
        urls = {}
        for c in CHECKS:
            body = {"name": f"tst {c['id']}", "slug": f"tst-{c['id']}", "timeout": c["timeout"], "grace": c["grace"],
                    "desc": c["desc"], "tags": "tst " + ("urgent" if c["urgent"] else "summary"),
                    "channels": ",".join((tg + mail) if c["urgent"] else mail), "unique": ["name"]}
            r = await client.post(f"{API}/checks/", headers=hdr, json=body, timeout=TIMEOUT)
            if r.status_code in (401, 403):
                return {"ok": False, "note": "açar yalnız oxuma icazəlidir: yazma icazəli API açarı lazımdır"}
            r.raise_for_status()
            urls[c["id"]] = r.json()["ping_url"]
        self.db.put(URLS_KEY, json.dumps(urls))
        self.db.put(SPEC_KEY, spec)
        return {"ok": True, "note": f"{len(urls)} yoxlama quruldu; Telegram kanalı: {'var' if tg else 'YOXDUR'}"}

    # ---------- sending ----------
    async def _send(self, client: httpx.AsyncClient, url: str, state: str, msg: str) -> bool | None:
        """True sent; False to try again later; None: the check is gone on the account (set up again)."""
        suffix = {"ok": "", "start": "/start", "fail": "/fail"}[state]
        for i in range(TRIES):
            try:
                r = await client.post(url + suffix, content=msg.encode(), timeout=TIMEOUT)
                if r.status_code == 404:
                    return None
                if r.status_code < 500 and r.status_code != 429:
                    return r.status_code == 200
            except httpx.HTTPError:
                pass
            await asyncio.sleep(2 ** i)
        return False

    async def flush(self, client: httpx.AsyncClient) -> int:
        try:
            urls = json.loads(self.db.get(URLS_KEY) or "{}")
        except ValueError:
            urls = {}
        if not urls or not self.queue:
            return 0
        with self._lock:
            batch, self.queue = self.queue, []
        try:
            last = json.loads(self.db.get(LAST_KEY) or "{}")
        except ValueError:
            last = {}
        sent, again = 0, []
        for check, state, msg in batch:
            if check not in urls:
                continue
            ok = await self._send(client, urls[check], state, msg)
            if ok is None and time.time() - getattr(self, "_forced", 0.0) > 600:
                self._forced = time.time()     # deleted on the dashboard: set up again (at most every 10 minutes)
                self.db.delete(SPEC_KEY)
                self.need_setup = True
            if not ok:
                again.append((check, state, msg))
            sent += int(bool(ok))
            last[check] = {"ts": time.time(), "state": state, "msg": msg[:120], "delivered": bool(ok)}
        if again:                              # not lost: back in the queue unless a newer signal came meanwhile
            with self._lock:
                newer = {q[0] for q in self.queue}
                self.queue = [q for q in again if q[0] not in newer] + self.queue
        self.db.put(LAST_KEY, json.dumps(last, ensure_ascii=False))
        return sent

    async def run(self) -> None:
        """Background loop: set the account up when needed, then send queued signals every 5 seconds."""
        async with httpx.AsyncClient() as client:
            next_setup = 0.0
            self.need_setup = False
            while True:
                try:
                    if time.time() >= next_setup or self.need_setup:
                        self.need_setup = False
                        res = await self.setup(client)
                        self.db.put("hc:setup", json.dumps({"ts": time.time(), **res}, ensure_ascii=False))
                        next_setup = time.time() + (3600 if res.get("ok") else 600)
                    await self.flush(client)
                except Exception as e:      # the watcher itself never crashes the panel
                    log.warning("heartbeat: %s", type(e).__name__)
                    self.db.put("hc:setup", json.dumps({"ts": time.time(), "ok": False,
                                                        "note": f"xəta: {type(e).__name__}"}))
                    next_setup = time.time() + 600
                await asyncio.sleep(5)

    def view(self) -> dict:
        """For the diagnostics and Admin: is it set up, and each check's last signal (no addresses)."""
        try:
            setup = json.loads(self.db.get("hc:setup") or "null")
            last = json.loads(self.db.get(LAST_KEY) or "{}")
        except ValueError:
            setup, last = None, {}
        return {"key": bool(self._key()), "setup": setup, "checks": [
            {"id": c["id"], "urgent": c["urgent"], "last": last.get(c["id"])} for c in CHECKS]}


# ---------- what «alive» means for the panel and the price ----------
def alive_signals(heart: Heart, engine, now: float | None = None) -> None:
    """Every 5 minutes: app-alive (fresh price while the market is open) and price-feed (no metal OFFLINE). Quiet
    times are «skipped», not judged: the first 10 minutes after a start, the first 15 minutes after the market opens
    (daily and on Sunday), full exchange holidays; a «fail» needs 3 bad samples in a row."""
    from .candles import METALS
    from .engine import market_open
    now = time.time() if now is None else now
    why = ("bazar bağlıdır" if not market_open(now) else
           "bazar təzə açılıb" if not market_open(now - 900) else
           "birja bayramı" if holiday(now) or holiday(now + 6 * 3600) or early_close(now) else
           "panel təzə başlayıb" if now - heart.started < WARMUP else None)
    if why:
        heart.bad.clear()
        heart.skip("app-alive", why)
        heart.skip("price-feed", why)
        return
    age = now - (engine.last_ok if engine.last_ok is not None else heart.started)   # never a quote since the start
    off = [s for s in METALS if engine.status(s, now) == "OFFLINE"]
    for check, bad, ok_msg, bad_msg in (
            ("app-alive", age > 600, f"son qiymət {round(age)} san əvvəl", f"son qiymət {round(age / 60)} dəqiqə əvvəl"),
            ("price-feed", bool(off), "4/4 metal gəlir", "OFFLINE: " + ", ".join(off))):
        heart.bad[check] = heart.bad.get(check, 0) + 1 if bad else 0
        if heart.bad[check] >= BAD_IN_ROW:
            heart.beat(check, "fail", bad_msg)
        elif not bad:
            heart.beat(check, "ok", ok_msg)


_NY = ZoneInfo("America/New_York")


def _easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    return date(y, month, (h + l_ - 7 * m + 114) % 31 + 1)


def early_close(ts: float) -> bool:
    """The afternoon of a short day before a full holiday (24 Dec, 31 Dec, the Thursday before Good Friday): the
    market stops early, so from 13:00 New York a stale price is expected, not an outage."""
    d = datetime.fromtimestamp(ts, _NY)
    nxt = d + timedelta(days=1)
    if d.hour >= 13 and d.weekday() < 5 and holiday(nxt.replace(hour=12).timestamp()):
        return True
    # Thanksgiving (4th Thursday of November) and the day after: the US session stops early (seen 2026-11-26: the
    # Capital stream went quiet in the afternoon), so a quiet afternoon is not an outage
    tg = date(d.year, 11, 1) + timedelta(days=(3 - date(d.year, 11, 1).weekday()) % 7 + 21)
    return d.hour >= 13 and d.date() in (tg, tg + timedelta(days=1))


def holiday(ts: float) -> bool:
    """Days the metals do not trade at all (New Year, Good Friday, Christmas; the observed weekday when they fall on a
    weekend). Shortened days (Thanksgiving, July 4th ...) trade, so they are not here."""
    d = datetime.fromtimestamp(ts, _NY).date()
    days = set()
    for y in (d.year, d.year + 1):
        for x in (date(y, 1, 1), date(y, 12, 25)):
            days.add(x + timedelta(days=1) if x.weekday() == 6 else x - timedelta(days=1) if x.weekday() == 5 else x)
        days.add(_easter(y) - timedelta(days=2))
    return d in days


def deploy_signal(heart: Heart, log_path: str) -> None:
    """At start: the last line of data/update.log says whether the new version came up or was rolled back."""
    try:
        with open(log_path, encoding="utf-8") as f:
            lines = [x.strip() for x in f if x.strip()]
    except OSError:
        return
    if not lines:
        return
    last = lines[-1]
    if "rolled back" in last or last.split(" ", 2)[1:2] == ["held"]:   # rolled back, or held for owner approval
        if heart.db.get("hc:deploy_line") == last:    # the same rollback is reported once, not at every restart
            return
        heart.db.put("hc:deploy_line", last)
        heart.beat("deploy", "fail", last[:300])
    else:                                              # called at start and once a day: «the running version came up»
        heart.beat("deploy", "ok", last[:300])


# ---------- one shared watcher, so any job can send a signal without carrying a reference ----------
HEART: Heart | None = None


def beat(check: str, state: str = "ok", msg: str = "") -> None:
    if HEART is not None:
        HEART.beat(check, state, msg)


def skip(check: str, why: str) -> None:
    if HEART is not None:
        HEART.skip(check, why)
