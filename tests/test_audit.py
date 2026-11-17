"""Phase 0: the audit log is append-only and hash-chained."""
import sqlite3
from datetime import datetime, timezone

import pytest

from candleisgreen.core.audit import AuditLog

NOW = datetime(2026, 11, 16, 14, 40, tzinfo=timezone.utc)


def _fill(log, n=3):
    for i in range(n):
        log.append(event_type="test", entity_id=f"e{i}", payload={"i": i}, actor="tester",
                   strategy_version="v", event_time=NOW, received_time=NOW)


def test_chain_verifies_and_links(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite")
    _fill(log)
    records = log.records()
    assert log.verify() is None
    assert [r["seq"] for r in records] == [1, 2, 3]
    assert records[1]["prev_hash"] == records[0]["record_hash"]


def test_update_and_delete_are_refused(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite")
    _fill(log)
    conn = sqlite3.connect(log.path)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE audit_log SET actor = 'x' WHERE seq = 2")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM audit_log WHERE seq = 2")


def test_tampering_behind_the_triggers_is_detected(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite")
    _fill(log)
    conn = sqlite3.connect(log.path)
    conn.execute("DROP TRIGGER audit_no_update")
    conn.execute("UPDATE audit_log SET payload_json = '{\"i\":99}' WHERE seq = 2")
    conn.commit()
    assert log.verify() == 2


def test_removed_row_is_detected(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite")
    _fill(log)
    conn = sqlite3.connect(log.path)
    conn.execute("DROP TRIGGER audit_no_delete")
    conn.execute("DELETE FROM audit_log WHERE seq = 2")
    conn.commit()
    assert log.verify() == 2


def test_log_survives_reopen(tmp_path):
    path = tmp_path / "audit.sqlite"
    first = AuditLog(path)
    _fill(first, 2)
    first.close()
    second = AuditLog(path)
    _fill(second, 1)
    assert len(second.records()) == 3 and second.verify() is None
