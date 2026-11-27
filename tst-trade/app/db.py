"""SQLite storage: ticks, candles, forecasts and their scores, saved keys and settings."""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS ticks (
  symbol TEXT NOT NULL, ts REAL NOT NULL, price REAL NOT NULL, source TEXT NOT NULL, source_ts REAL
);
CREATE INDEX IF NOT EXISTS ticks_sym_ts ON ticks(symbol, ts);
CREATE TABLE IF NOT EXISTS candles (
  symbol TEXT NOT NULL, tf TEXT NOT NULL, t INTEGER NOT NULL,
  o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL, origin TEXT NOT NULL DEFAULT 'live',
  PRIMARY KEY (symbol, tf, t)
);
CREATE TABLE IF NOT EXISTS forecasts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL, horizon TEXT NOT NULL, method TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'live',
  issued_t INTEGER NOT NULL, target_t INTEGER NOT NULL, price0 REAL NOT NULL,
  p_up REAL NOT NULL, lo50 REAL NOT NULL, hi50 REAL NOT NULL, lo80 REAL NOT NULL, hi80 REAL NOT NULL,
  basis TEXT NOT NULL DEFAULT '',
  price1 REAL, scored_ts REAL, outcome INTEGER, hit INTEGER, brier REAL, in50 INTEGER, in80 INTEGER,
  UNIQUE (symbol, horizon, method, mode, issued_t)
);
CREATE INDEX IF NOT EXISTS fc_open ON forecasts(scored_ts, target_t);
CREATE INDEX IF NOT EXISTS fc_stats ON forecasts(symbol, horizon, mode, method);
CREATE INDEX IF NOT EXISTS fc_recent ON forecasts(symbol, mode, target_t);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


class Rows:
    """A finished query: its rows were read while the lock was held. The one shared connection is used by the event
    loop and by worker threads; a cursor read after the lock is released can be overwritten by another thread's
    statement (seen 2026-11-24: «IndexError: tuple index out of range» inside fetchall). Behaves like a cursor for
    fetchone / fetchall / iteration, and keeps rowcount and lastrowid of writes."""
    __slots__ = ("rows", "rowcount", "lastrowid", "_i")

    def __init__(self, rows: list, rowcount: int = -1, lastrowid: int | None = None):
        self.rows, self.rowcount, self.lastrowid, self._i = rows, rowcount, lastrowid, 0

    def fetchone(self):
        if self._i < len(self.rows):
            self._i += 1
            return self.rows[self._i - 1]
        return None

    def fetchall(self) -> list:
        out = self.rows[self._i:]
        self._i = len(self.rows)
        return out

    def fetchmany(self, n: int = 1000) -> list:
        out = self.rows[self._i:self._i + n]
        self._i += len(out)
        return out

    def __iter__(self):
        while self._i < len(self.rows):
            self._i += 1
            yield self.rows[self._i - 1]

    def __getitem__(self, i):
        return self.rows[i]


_READ = re.compile(r"\s*(SELECT|WITH)\b", re.I)
_WRITE = re.compile(r"\b(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER)\b", re.I)


class DB:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._local = threading.local()
        self.conn.executescript(SCHEMA)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(candles)").fetchall()}
        if "v" not in cols:          # tick volume (2026-11-25): how many times the price changed inside the candle
            self.conn.execute("ALTER TABLE candles ADD COLUMN v INTEGER")
        fcols = {r[1] for r in self.conn.execute("PRAGMA table_info(forecasts)").fetchall()}
        if "created_ts" not in fcols:   # 27.11: when the row was really written (the Judge's look-ahead guard)
            self.conn.execute("ALTER TABLE forecasts ADD COLUMN created_ts REAL")

    def script(self, sql: str) -> None:
        """Schema statements under the same lock as every write. sqlite's executescript COMMITs first: run unlocked
        from another thread it would end a running executemany transaction halfway («cannot commit - no
        transaction is active»), so nothing may call conn.executescript directly."""
        with self.lock:
            self.conn.executescript(sql)

    def _reader(self) -> sqlite3.Connection:
        """This thread's own read-only connection (2026-11-25: the site froze while a long report read the 1 GB
        database, because every read waited for the one shared lock and the web handlers' small reads queued behind
        it). WAL lets any number of readers work beside the one writer; reads see everything already committed."""
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA busy_timeout=5000")
            self._local.conn = c
        return c

    def execute(self, sql: str, args: tuple | list = ()) -> Rows:
        """Run one statement and read its rows. A plain read (SELECT / WITH ... SELECT) goes through this thread's own
        read connection without the lock; every write and schema statement holds the lock on the one writer
        connection (see Rows). For very large reads use iterate."""
        if self.path != ":memory:" and _READ.match(sql) and not _WRITE.search(sql):
            cur = self._reader().execute(sql, args)
            return Rows(cur.fetchall(), cur.rowcount, cur.lastrowid)
        with self.lock:
            cur = self.conn.execute(sql, args)
            rows = cur.fetchall() if cur.description is not None else []
            return Rows(rows, cur.rowcount, cur.lastrowid)

    def iterate(self, sql: str, args: tuple | list = (), size: int = 5000):
        """Stream a large read (hundreds of thousands of rows) through its own short-lived connection: WAL lets it
        read while others write, nothing is shared, and memory stays small. An in-memory database (tests) has no
        second connection: it is read through execute."""
        if self.path == ":memory:":
            yield from self.execute(sql, args)
            return
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(sql, args)
            while True:
                chunk = cur.fetchmany(size)
                if not chunk:
                    break
                yield from chunk
        finally:
            conn.close()

    def executemany(self, sql: str, rows) -> None:
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                self.conn.executemany(sql, rows)
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def get(self, k: str, default: str | None = None) -> str | None:
        row = self.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return row["v"] if row else default

    def put(self, k: str, v: str) -> None:
        self.execute("INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))

    def delete(self, k: str) -> None:
        self.execute("DELETE FROM kv WHERE k=?", (k,))
