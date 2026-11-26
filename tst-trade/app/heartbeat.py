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
import json
import logging
import time

import httpx

from .db import DB

log = logging.getLogger("tst.heartbeat")

API = "https://healthchecks.io/api/v3"
SLOT = "healthchecks"
URLS_KEY, LAST_KEY, SPEC_KEY = "hc:urls", "hc:last", "hc:spec"
TIMEOUT, TRIES = 10.0, 3
H = 3600

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
        self._task: asyncio.Task | None = None

    # ---------- the jobs call this ----------
    def beat(self, check: str, state: str = "ok", msg: str = "") -> None:
        """Queue a signal: state «ok», «start» or «fail». Never blocks, never raises."""
        try:
            if check in IDS and state in ("ok", "start", "fail"):
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
        spec = json.dumps(CHECKS, sort_keys=True) + key[-6:]
        if self.db.get(SPEC_KEY) == spec and self.db.get(URLS_KEY):
            return {"ok": True, "note": "hazırdır"}
        hdr = {"X-Api-Key": key}
        r = await client.get(f"{API}/channels/", headers=hdr, timeout=TIMEOUT)
        r.raise_for_status()
        chans = r.json().get("channels", [])
        tg = [c["id"] for c in chans if c.get("kind") == "telegram"]
        mail = [c["id"] for c in chans if c.get("kind") == "email"]
        urls = {}
        for c in CHECKS:
            body = {"name": f"tst {c['id']}", "slug": f"tst-{c['id']}", "timeout": c["timeout"], "grace": c["grace"],
                    "desc": c["desc"], "tags": "tst " + ("urgent" if c["urgent"] else "summary"),
                    "channels": ",".join((tg + mail) if c["urgent"] else mail), "unique": ["name"]}
            r = await client.post(f"{API}/checks/", headers=hdr, json=body, timeout=TIMEOUT)
            r.raise_for_status()
            urls[c["id"]] = r.json()["ping_url"]
        self.db.put(URLS_KEY, json.dumps(urls))
        self.db.put(SPEC_KEY, spec)
        return {"ok": True, "note": f"{len(urls)} yoxlama quruldu; Telegram kanalı: {'var' if tg else 'YOXDUR'}"}

    # ---------- sending ----------
    async def _send(self, client: httpx.AsyncClient, url: str, state: str, msg: str) -> bool:
        suffix = {"ok": "", "start": "/start", "fail": "/fail"}[state]
        for i in range(TRIES):
            try:
                r = await client.post(url + suffix, content=msg.encode(), timeout=TIMEOUT)
                if r.status_code < 500:
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
        batch, self.queue = self.queue, []
        last = json.loads(self.db.get(LAST_KEY) or "{}")
        sent = 0
        for check, state, msg in batch:
            if check not in urls:
                continue
            ok = await self._send(client, urls[check], state, msg)
            sent += int(ok)
            last[check] = {"ts": time.time(), "state": state, "msg": msg[:120], "delivered": ok}
        self.db.put(LAST_KEY, json.dumps(last, ensure_ascii=False))
        return sent

    async def run(self) -> None:
        """Background loop: set the account up when needed, then send queued signals every 5 seconds."""
        async with httpx.AsyncClient() as client:
            next_setup = 0.0
            while True:
                try:
                    if time.time() >= next_setup:
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
    """Every 5 minutes: app-alive (fresh price while the market is open) and price-feed (no metal OFFLINE)."""
    from .candles import METALS
    from .engine import market_open
    now = time.time() if now is None else now
    if not market_open(now):
        heart.skip("app-alive", "bazar bağlıdır")
        heart.skip("price-feed", "bazar bağlıdır")
        return
    age = now - (engine.last_ok or 0)
    if age > 600:
        heart.beat("app-alive", "fail", f"son qiymət {round(age / 60)} dəqiqə əvvəl")
    else:
        heart.beat("app-alive", "ok", f"son qiymət {round(age)} san əvvəl")
    off = [s for s in METALS if engine.status(s, now) == "OFFLINE"]
    if off:
        heart.beat("price-feed", "fail", "OFFLINE: " + ", ".join(off))
    else:
        heart.beat("price-feed", "ok", "4/4 metal gəlir")


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
    if "rolled back" in last:
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
