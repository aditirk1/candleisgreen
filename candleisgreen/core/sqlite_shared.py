"""One SQLite connection shared by API worker threads.

Each statement runs and is fully fetched under a lock, so two requests never interleave on the
connection. Stores here use autocommit and single statements, so no transaction spans calls.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable


class _Result:
    def __init__(self, cur: sqlite3.Cursor):
        self._rows = cur.fetchall()
        self.description = cur.description
        self.lastrowid = cur.lastrowid
        self.rowcount = cur.rowcount

    def fetchall(self) -> list:
        rows, self._rows = self._rows, []
        return rows

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def __iter__(self):
        return iter(self.fetchall())


class LockedConnection:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = threading.RLock()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> _Result:
        with self._lock:
            return _Result(self._conn.execute(sql, tuple(params) if not isinstance(params, dict) else params))

    def executemany(self, sql: str, seq) -> _Result:
        with self._lock:
            return _Result(self._conn.executemany(sql, seq))

    def executescript(self, script: str) -> None:
        with self._lock:
            self._conn.executescript(script)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def connect(path: str | Path, shared_across_threads: bool = False):
    """Autocommit connection. Shared connections are wrapped in a lock."""
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=not shared_across_threads)
    return LockedConnection(conn) if shared_across_threads else conn
