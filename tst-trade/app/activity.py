"""The one central place where every agent writes its status; the agents panel only reads from here.

An agent calls report(task, status, ...) when it starts, at each stage (W1, W2, ...) and when it finishes. Each call
is appended to the agent_events table (kept 7 days: the panel's timeline and replay read it) and updates the current
state held in memory; open panels receive it at once over a WebSocket. Agents never read each other's state and the
panel never touches the agents: data flows one way, agent -> here -> panel.

The map of tasks (NODES) is fixed in code: number, short name, which task it depends on, its stages. A task that is
not in the map cannot report, so the picture always matches the real system."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

from .db import DB

log = logging.getLogger("tst.activity")
SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_events (ts REAL NOT NULL, task TEXT NOT NULL, status TEXT NOT NULL,
  stage TEXT, progress REAL, note TEXT, seq INTEGER, src TEXT);
CREATE INDEX IF NOT EXISTS agent_events_ts ON agent_events(ts);
"""
KEEP = 7 * 86400
STATUSES = ("waiting", "working", "done", "error")

# id: (number, short name, depends on, stages, what it does)
NODES = {
    "orch":     (0,  "Orkestrator",        None,       [],                                   "Baş dövr: hər 15 saniyədə bütün işləri növbə ilə çağırır"),
    "prices":   (1,  "Qiymət axını",       "orch",     [],                                   "Capital.com: 4 metal və 8 bazar, saniyə-saniyə"),
    "forecast": (2,  "Proqnoz masaları",   "prices",   [],                                   "Şam bağlananda hər üfüq və üsul üzrə proqnoz"),
    "judge":    (3,  "Hakim",              "forecast", [],                                   "Vaxtı çatan proqnozları yoxlayır"),
    "history":  (4,  "Tarixçə",            "orch",     ["W1 Capital", "W2 Twelve Data", "W3 Yenidən hesab", "W4 Hakim"],
                 "Keçmiş şamları yükləyir və proqnozları keçmiş üzərində yenidən hesablayır"),
    "news":     (5,  "Xəbər lentləri",     "orch",     [],                                   "Google News, Fed, Benzinga"),
    "calendar": (6,  "İqtisadi təqvim",    "orch",     [],                                   "Forex Factory: ABŞ rəqəmlərinin vaxtı və gözləntisi"),
    "macro":    (7,  "Makro və COT",       "orch",     [],                                   "FRED (faiz, dollar, VIX) və CFTC COT"),
    "reader":   (8,  "Oxuyucu",            "news",     [],                                   "Beyin: başlığı qiymətləndirir (metal, istiqamət, güc)"),
    "scout":    (9,  "Kəşfiyyatçı",        "orch",     [],                                   "Beyin (Grok): X-də son xəbərləri axtarır"),
    "hunter":   (10, "Rəqəm ovçusu",       "calendar", ["W1 Rəqəm çıxdı", "W2 İki beyin axtarır", "W3 Müqayisə"],
                 "İki beyin ABŞ rəqəminin faktını vebdə ayrı-ayrı tapır"),
    "signals":  (12, "Sinirlər",           "reader",   [],
                 "Siqnal lenti: güclü xəbər, xəbər axını, ABŞ rəqəmi, qəfil sıçrayış → həyəcan"),
    "strateq":  (11, "Strateq",            "signals",  ["W1 Faktlar", "W2 Beyin", "W3 Rəqəm yoxlaması", "W4 Yaddaş"],
                 "Beyin (Claude): saatda bir və hər həyəcanda 1 saat, 4 saat, 1 gün ehtimalı"),
    "debate":   (13, "Müzakirə",           "signals",  ["W1 Yuxarı tərəfdarı", "W2 Aşağı tərəfdarı", "W3 Hakim beyin"],
                 "İki beyin yuxarı və aşağı üçün dəlil gətirir, üçüncüsü tərəzidə çəkib ehtimal verir"),
    "liquidity": (14, "Likvidlik",         "prices",   [],
                  "Spred və bazar fəallığı: nazik bazarda proqnoz baha başa gəlir"),
    "risk":     (15, "Risk qapısı",        "liquidity", [],
                 "Köhnə qiymət, ABŞ rəqəmi ərəfəsi, nazik və ya vəhşi bazar → istiqamət göstərilmir"),
    "decision": (16, "Qərar",              "judge",    [],
                 "AL / SAT yalnız Hakimin sübutu və açıq risk qapısı ilə; əks halda GÖZLƏ (yalnız göstərici)"),
    "events":   (17, "Hadisə birləşdiricisi", "news",  [],
                 "Eyni xəbəri yazan saytları bir hadisəyə yığır: Oxuyucu yalnız birincisini oxuyur"),
    "cards":    (18, "Jurnal katibi",      "strateq",  [],
                 "Hər proqnozu dondurur: ssenari, əks ssenari, zəifləmə şərti, məlumat keyfiyyəti, versiya"),
    "checker":  (19, "Mənbə yoxlayıcısı",  "strateq",  [],
                 "Beyin cavabında ona verilməyən rəqəmləri sayır (uydurma göstərilmir)"),
    "ta":       (22, "Texniki analiz bloku", "prices", [],
                 "Kod: 12 növ, 34 qayda qrafikdə tapılır, Hakim hər qaydanı ölçür, proqnoza bir səs («Qaydalar»)"),
    "chartist": (21, "Qrafik analitiki",   "ta",  ["W1 Şamlar", "W2 Beyin", "W3 Yaddaş"],
                 "Beyin: qrafikə özü baxır (3 vaxt çərçivəsi, səviyyələr, fiqurlar), 1 saat / 4 saat / 1 gün ehtimalı"),
    "archivist": (20, "Arxivçi",           "macro",    [],
                  "ALFRED: rəqəmin ilk dərc olunmuş dəyəri, sonrakı düzəlişlər keçmiş sınağa qarışmasın"),
}

# Block 17: where each task's input comes FROM (the data flow, not the call tree). The panel draws a courier from
# the source to the task when the task reports; a task may also name its source itself (report(..., src=...)).
FLOW = {"prices": None, "liquidity": "prices", "forecast": "prices", "judge": "forecast", "history": "orch",
        "news": None, "events": "news", "reader": "events", "calendar": None, "hunter": "calendar", "macro": None,
        "scout": None, "signals": "reader", "strateq": "signals", "debate": "strateq", "cards": "strateq",
        "checker": "strateq", "risk": "liquidity", "decision": "risk", "orch": None, "archivist": "macro", "chartist": "ta", "ta": "prices"}


class Hub:
    def __init__(self, db: DB):
        self.db = db
        db.script(SCHEMA)
        cols = {r[1] for r in db.execute("PRAGMA table_info(agent_events)").fetchall()}
        for c, t in (("seq", "INTEGER"), ("src", "TEXT")):          # Block 17: older tables gain the columns
            if c not in cols:
                db.execute(f"ALTER TABLE agent_events ADD COLUMN {c} {t}")
        self.seq = db.execute("SELECT MAX(seq) m FROM agent_events").fetchone()["m"] or 0
        self.state: dict[str, dict] = {k: {"task": k, "status": "waiting", "stage": None, "progress": None,
                                           "note": "", "ts": None, "done_ts": None} for k in NODES}
        self.subscribers: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self.last_prune = 0.0

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def report(self, task: str, status: str, stage: str | None = None, progress: float | None = None,
               note: str = "", src: str | None = None) -> None:
        """Called by an agent (from the event loop or a worker thread). Never raises: reporting must not break work.
        Every event gets a sequence number (gaps show a lost event) and the task its data came from (src)."""
        try:
            if task not in NODES or status not in STATUSES:
                return
            now = time.time()
            src = src if src in NODES else FLOW.get(task)
            with self._lock:
                self.seq += 1
                seq = self.seq
            ev = {"ts": now, "task": task, "status": status, "stage": stage, "seq": seq, "src": src,
                  "progress": None if progress is None else round(max(0.0, min(1.0, progress)), 3), "note": note[:160]}
            with self._lock:
                st = self.state[task]
                st.update({k: ev[k] for k in ("status", "stage", "progress", "note", "ts")})
                if status == "done":
                    st["done_ts"] = now
            self.db.execute("INSERT INTO agent_events(ts, task, status, stage, progress, note, seq, src) "
                            "VALUES(?,?,?,?,?,?,?,?)", (now, task, status, stage, ev["progress"], ev["note"], seq, src))
            if now - self.last_prune > 3600:
                self.last_prune = now
                self.db.execute("DELETE FROM agent_events WHERE ts < ?", (now - KEEP,))
            self._publish(ev)
        except Exception:
            log.exception("activity report failed")

    def _publish(self, ev: dict) -> None:
        if not self.subscribers or self.loop is None:
            return
        msg = json.dumps({"type": "event", "event": ev})

        def push():
            for q in list(self.subscribers):
                if q.qsize() < 500:          # a stuck viewer must not grow memory without end
                    q.put_nowait(msg)
        try:
            if threading.current_thread() is threading.main_thread():
                push()
            else:
                self.loop.call_soon_threadsafe(push)
        except RuntimeError:
            pass

    def snapshot(self) -> dict:
        with self._lock:
            state = {k: dict(v) for k, v in self.state.items()}
        nodes = [{"id": k, "num": n, "name": name, "parent": parent, "stages": stages, "what": what, "src": FLOW.get(k)}
                 for k, (n, name, parent, stages, what) in NODES.items()]
        return {"type": "snapshot", "nodes": nodes, "state": state, "now": time.time()}

    def events(self, since: float, limit: int = 20000) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT ts, task, status, stage, progress, note, seq, src FROM agent_events WHERE ts >= ? ORDER BY ts LIMIT ?",
            (since, limit)).fetchall()]


class Stages:
    """A task with stages: `with Stages(hub, "history") as s: s.stage("W1 Capital", 0.3)` -> working ... done/error."""
    def __init__(self, hub: "Hub | None", task: str):
        self.hub, self.task = hub, task

    def __enter__(self):
        if self.hub:
            self.hub.report(self.task, "working", note="başladı")
        return self

    def stage(self, stage: str, progress: float | None = None, note: str = "") -> None:
        if self.hub:
            self.hub.report(self.task, "working", stage, progress, note)

    def __exit__(self, exc_type, exc, tb):
        if self.hub:
            if exc_type is None:
                self.hub.report(self.task, "done", note="bitdi")
            else:
                self.hub.report(self.task, "error", note=f"{exc_type.__name__}: {str(exc)[:120]}")
        return False
