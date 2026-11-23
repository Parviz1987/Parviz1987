"""SQLite storage: ticks, candles, forecasts and their scores, saved keys and settings."""
from __future__ import annotations

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
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


class DB:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.conn.executescript(SCHEMA)

    def execute(self, sql: str, args: tuple | list = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, args)

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
