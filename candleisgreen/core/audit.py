"""Append-only, hash-chained audit log on SQLite.

Each record stores the hash of the previous record. Editing or deleting any row breaks the
chain and `verify` reports the first bad sequence number. SQL triggers refuse UPDATE and
DELETE, so a normal connection cannot rewrite history.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .ids import canonical_json, sha256_hex
from .timeutil import iso_utc

GENESIS_HASH = "0" * 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY,
    event_time_utc TEXT NOT NULL,
    received_time_utc TEXT NOT NULL,
    actor TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    event_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""


def _record_hash(prev_hash: str, body: dict[str, Any]) -> str:
    return sha256_hex(prev_hash + canonical_json(body))


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def _last(self) -> tuple[int, str]:
        row = self._conn.execute("SELECT seq, record_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        return (row[0], row[1]) if row else (0, GENESIS_HASH)

    def append(
        self,
        *,
        event_type: str,
        entity_id: str,
        payload: Any,
        actor: str,
        strategy_version: str,
        event_time: datetime,
        received_time: datetime,
    ) -> str:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            last_seq, prev_hash = self._last()
            body = {
                "seq": last_seq + 1,
                "event_time_utc": iso_utc(event_time),
                "received_time_utc": iso_utc(received_time),
                "actor": actor,
                "strategy_version": strategy_version,
                "event_type": event_type,
                "entity_id": entity_id,
                "payload_json": canonical_json(payload),
            }
            record_hash = _record_hash(prev_hash, body)
            self._conn.execute(
                "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?,?,?)",
                (*body.values(), prev_hash, record_hash),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return record_hash

    def records(self) -> list[dict[str, Any]]:
        cur = self._conn.execute("SELECT * FROM audit_log ORDER BY seq")
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def verify(self) -> Optional[int]:
        """Return None when the chain is intact, else the first bad sequence number."""
        prev_hash = GENESIS_HASH
        expected_seq = 1
        for rec in self.records():
            body = {k: rec[k] for k in rec if k not in ("prev_hash", "record_hash")}
            if rec["seq"] != expected_seq or rec["prev_hash"] != prev_hash:
                return expected_seq
            if _record_hash(prev_hash, body) != rec["record_hash"]:
                return rec["seq"]
            prev_hash = rec["record_hash"]
            expected_seq += 1
        return None
