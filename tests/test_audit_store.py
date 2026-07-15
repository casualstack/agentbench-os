"""Tests for AuditStore: append/read round trip and tamper detection."""

from __future__ import annotations

import sqlite3

import pytest

from agentbench.accountability.audit.store import AuditStore


def _record(**overrides):
    record = {
        "ts": "2026-07-15T00:00:00Z",
        "agent": "claude-code",
        "session_id": "s1",
        "cwd": "C:\\work\\myrepo",
        "model": "claude-x",
        "step_index": 0,
        "rule": "deleted_assertion",
        "severity": "critical",
        "title": "Deleted a test assertion",
        "detail": "The agent removed a check.",
        "path": "tests/test_calc.py",
        "source_path": "C:\\home\\.claude\\projects\\p\\s1.jsonl",
        "source_size": 1234,
        "source_mtime": 1700000000.0,
    }
    record.update(overrides)
    return record


@pytest.fixture
def store(tmp_path):
    with AuditStore(tmp_path / "audit.db") as s:
        yield s


def test_append_returns_sequential_ids(store):
    assert store.append(_record()) == 1
    assert store.append(_record(rule="skipped_test")) == 2
    assert store.append(_record(rule="hook_bypass")) == 3


def test_append_creates_db_file(tmp_path):
    db_path = tmp_path / "nested" / "audit.db"
    with AuditStore(db_path) as s:
        s.append(_record())
    assert db_path.exists()


def test_iter_events_round_trip(store):
    store.append(_record(session_id="s1", rule="deleted_assertion"))
    store.append(_record(session_id="s2", rule="skipped_test"))

    events = list(store.iter_events())
    assert [e["rule"] for e in events] == ["deleted_assertion", "skipped_test"]
    assert events[0]["id"] == 1
    assert events[1]["id"] == 2
    assert events[0]["prev_hash"] == "GENESIS"
    assert events[1]["prev_hash"] == events[0]["record_hash"]


def test_iter_events_filters_by_agent(store):
    store.append(_record(agent="claude-code"))
    store.append(_record(agent="codex"))
    assert [e["agent"] for e in store.iter_events(agent="codex")] == ["codex"]


def test_iter_events_filters_by_session_id(store):
    store.append(_record(session_id="s1"))
    store.append(_record(session_id="s2"))
    assert [e["session_id"] for e in store.iter_events(session_id="s2")] == ["s2"]


def test_iter_events_filters_by_severity(store):
    store.append(_record(severity="critical"))
    store.append(_record(severity="warning"))
    assert [e["severity"] for e in store.iter_events(severity="warning")] == ["warning"]


def test_iter_events_filters_by_project(store):
    store.append(_record(cwd="C:\\work\\repo-a"))
    store.append(_record(cwd="C:\\work\\repo-b"))
    events = list(store.iter_events(project="C:\\work\\repo-a"))
    assert len(events) == 1
    assert events[0]["cwd"] == "C:\\work\\repo-a"


def test_iter_events_filters_by_since(store):
    store.append(_record(ts="2026-07-15T00:00:00Z"))
    store.append(_record(ts="2026-07-16T00:00:00Z"))
    events = list(store.iter_events(since="2026-07-16T00:00:00Z"))
    assert len(events) == 1
    assert events[0]["ts"] == "2026-07-16T00:00:00Z"


def test_verify_ok_on_untouched_store(store):
    for i in range(5):
        store.append(_record(rule=f"rule_{i}"))
    assert store.verify() is None


def test_verify_ok_on_empty_store(store):
    assert store.verify() is None


def test_verify_catches_direct_row_tamper(tmp_path):
    db_path = tmp_path / "audit.db"
    with AuditStore(db_path) as s:
        s.append(_record())
        s.append(_record(rule="skipped_test"))
        s.append(_record(rule="hook_bypass"))

    # Tamper with row id=2 directly via raw sqlite3, bypassing AuditStore
    # entirely -- this is the exact "did someone edit the db after the
    # fact" scenario the hash chain exists to catch.
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE events SET detail = 'edited' WHERE id = 2")
    conn.commit()
    conn.close()

    with AuditStore(db_path) as s:
        assert s.verify() == 2


def test_verify_catches_deleted_row(tmp_path):
    db_path = tmp_path / "audit.db"
    with AuditStore(db_path) as s:
        s.append(_record())
        s.append(_record(rule="skipped_test"))
        s.append(_record(rule="hook_bypass"))

    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM events WHERE id = 2")
    conn.commit()
    conn.close()

    with AuditStore(db_path) as s:
        # Row 3's prev_hash no longer matches row 1's record_hash once
        # row 2 is gone, so verification breaks at row 3.
        assert s.verify() == 3
