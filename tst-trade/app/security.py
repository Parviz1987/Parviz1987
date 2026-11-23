"""Security: stop password guessing, keep a journal of every sensitive event, and flag what the owner must see.

- A wrong password costs the address a slot: 5 wrong tries in 15 minutes block that address for 15 minutes (HTTP
  429), so a bot cannot guess; the owner's other devices are not affected. The same for wrong diagnostics tokens.
- Journal (sec_events): failed and blocked logins, logins from a new address, key saved or deleted, password and
  guest password changes, price source changes. Secrets are never written, only what happened and from where.
- alerts(): what the on-duty monitor reports to the owner's phone (a login from a new address, an attack, a key
  change the owner may not have made)."""
from __future__ import annotations

import time

from .db import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS sec_events (ts REAL NOT NULL, kind TEXT NOT NULL, ip TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS sec_events_ts ON sec_events(ts);
CREATE TABLE IF NOT EXISTS known_ips (ip TEXT PRIMARY KEY, first_ts REAL, last_ts REAL, role TEXT);
"""
WINDOW, MAX_FAILS, BLOCK = 15 * 60, 5, 15 * 60
KEEP = 90 * 86400
KIND_AZ = {"login_fail": "səhv parol", "login_blocked": "bloklanıb (çox səhv cəhd)", "login_new_ip": "yeni ünvandan giriş",
           "login_ok": "giriş", "diag_bad_token": "səhv diaqnostika açarı", "key_saved": "açar saxlanıb",
           "key_deleted": "açar silinib", "password_changed": "parol dəyişib", "guest_changed": "qonaq parolu dəyişib",
           "provider_changed": "qiymət mənbəyi dəyişib", "diag_token_changed": "diaqnostika açarı dəyişib"}
ALERT = ("login_blocked", "login_new_ip", "key_deleted", "password_changed", "diag_token_changed", "key_saved")


class Guard:
    def __init__(self, db: DB):
        self.db = db
        db.conn.executescript(SCHEMA)
        self.fails: dict[str, list[float]] = {}
        self.blocked: dict[str, float] = {}

    def log(self, kind: str, ip: str | None, detail: str = "") -> None:
        self.db.execute("INSERT INTO sec_events VALUES(?,?,?,?)", (time.time(), kind, ip or "", detail[:200]))

    def is_blocked(self, ip: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return self.blocked.get(ip, 0) > now

    def failed(self, ip: str, what: str = "login", now: float | None = None) -> None:
        now = time.time() if now is None else now
        tries = [t for t in self.fails.get(ip, []) if now - t < WINDOW] + [now]
        self.fails[ip] = tries
        self.log("login_fail" if what == "login" else "diag_bad_token", ip)
        if len(tries) >= MAX_FAILS:
            self.blocked[ip] = now + BLOCK
            self.fails[ip] = []
            self.log("login_blocked", ip, f"{MAX_FAILS} səhv cəhd {WINDOW // 60} dəqiqədə ({what})")

    def succeeded(self, ip: str, role: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self.fails.pop(ip, None)
        seen = self.db.execute("SELECT 1 FROM known_ips WHERE ip=?", (ip,)).fetchone()
        any_known = self.db.execute("SELECT 1 FROM known_ips LIMIT 1").fetchone()
        self.db.execute("INSERT INTO known_ips VALUES(?,?,?,?) ON CONFLICT(ip) DO UPDATE SET last_ts=excluded.last_ts",
                        (ip, now, now, role))
        # The very first login only teaches the owner's address; afterwards a new address is worth a look.
        self.log("login_new_ip" if (any_known and not seen) else "login_ok", ip, role)

    def prune(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self.db.execute("DELETE FROM sec_events WHERE ts < ?", (now - KEEP,))

    def summary(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        counts = {r["kind"]: r["n"] for r in self.db.execute(
            "SELECT kind, COUNT(*) n FROM sec_events WHERE ts > ? GROUP BY kind", (now - 86400,)).fetchall()}
        alerts = [dict(r) for r in self.db.execute(
            f"SELECT ts, kind, ip, detail FROM sec_events WHERE ts > ? AND kind IN ({','.join('?' * len(ALERT))}) "
            "ORDER BY ts DESC LIMIT 20", (now - 86400, *ALERT)).fetchall()]
        return {"last_24h": counts, "alerts": alerts, "blocked_now": [ip for ip, t in self.blocked.items() if t > now],
                "known_ips": self.db.execute("SELECT COUNT(*) FROM known_ips").fetchone()[0]}

    def recent(self, limit: int = 30) -> list[dict]:
        return [{**dict(r), "kind_az": KIND_AZ.get(r["kind"], r["kind"])} for r in self.db.execute(
            "SELECT ts, kind, ip, detail FROM sec_events ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()]
