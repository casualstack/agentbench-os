"""Tests for the incident backlog: 1:1 alert->incident, status transitions."""

from __future__ import annotations

import pytest

from agentbench.accountability.audit.incidents import (
    ACKNOWLEDGED,
    OPEN,
    RESOLVED,
    IncidentStore,
    incident_id_for,
)
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
def db_path(tmp_path):
    return tmp_path / "audit.db"


def test_incident_id_is_stable_for_the_same_signature():
    a = incident_id_for("s1", 0, "deleted_assertion")
    b = incident_id_for("s1", 0, "deleted_assertion")
    assert a == b


def test_incident_id_differs_across_signatures():
    a = incident_id_for("s1", 0, "deleted_assertion")
    b = incident_id_for("s1", 1, "deleted_assertion")
    c = incident_id_for("s1", 0, "skipped_test")
    assert len({a, b, c}) == 3


def test_sync_creates_one_incident_per_event(db_path):
    with AuditStore(db_path) as audit:
        audit.append(_record())
        audit.append(_record(step_index=1, rule="skipped_test"))

    with IncidentStore(db_path) as incidents:
        created = incidents.sync()
        assert created == 2
        assert len(incidents.list()) == 2

    for incident in IncidentStore(db_path).list():
        assert incident.status == OPEN


def test_incidents_default_to_open_status(db_path):
    with AuditStore(db_path) as audit:
        audit.append(_record())

    with IncidentStore(db_path) as incidents:
        [incident] = incidents.list()
        assert incident.status == OPEN
        assert incident.title == "Deleted a test assertion"
        assert incident.session_id == "s1"


def test_acknowledge_transitions_status_and_keeps_note(db_path):
    with AuditStore(db_path) as audit:
        audit.append(_record())

    with IncidentStore(db_path) as incidents:
        [incident] = incidents.list()
        updated = incidents.acknowledge(incident.incident_id, note="reviewed")
        assert updated is not None
        assert updated.status == ACKNOWLEDGED
        assert updated.note == "reviewed"
        assert updated.resolved_at is None


def test_resolve_transitions_status_and_sets_resolved_at(db_path):
    with AuditStore(db_path) as audit:
        audit.append(_record())

    with IncidentStore(db_path) as incidents:
        [incident] = incidents.list()
        updated = incidents.resolve(incident.incident_id, note="fixed")
        assert updated is not None
        assert updated.status == RESOLVED
        assert updated.note == "fixed"
        assert updated.resolved_at is not None


def test_get_unknown_incident_returns_none(db_path):
    with IncidentStore(db_path) as incidents:
        assert incidents.get("nonexistent") is None


def test_ack_unknown_incident_returns_none(db_path):
    with IncidentStore(db_path) as incidents:
        assert incidents.acknowledge("nonexistent") is None


def test_list_filters_by_status(db_path):
    with AuditStore(db_path) as audit:
        audit.append(_record(step_index=0))
        audit.append(_record(step_index=1, rule="skipped_test"))

    with IncidentStore(db_path) as incidents:
        all_incidents = incidents.list()
        incidents.resolve(all_incidents[0].incident_id)

        open_only = incidents.list(status=OPEN)
        resolved_only = incidents.list(status=RESOLVED)
        assert len(open_only) == 1
        assert len(resolved_only) == 1
        assert open_only[0].incident_id == all_incidents[1].incident_id
        assert resolved_only[0].incident_id == all_incidents[0].incident_id


def test_list_filters_by_severity(db_path):
    with AuditStore(db_path) as audit:
        audit.append(_record(step_index=0, severity="critical"))
        audit.append(_record(step_index=1, severity="warning", rule="network_command"))

    with IncidentStore(db_path) as incidents:
        assert len(incidents.list(severity="critical")) == 1
        assert len(incidents.list(severity="warning")) == 1


def test_list_filters_by_project(db_path):
    with AuditStore(db_path) as audit:
        audit.append(_record(step_index=0, cwd="C:\\work\\repo-a"))
        audit.append(_record(step_index=1, cwd="C:\\work\\repo-b", rule="skipped_test"))

    with IncidentStore(db_path) as incidents:
        scoped = incidents.list(project="C:\\work\\repo-a")
        assert len(scoped) == 1
        assert scoped[0].cwd == "C:\\work\\repo-a"


def test_stable_incident_id_across_two_watch_runs(db_path):
    # Simulate `watch --once` run twice over the same session history: the
    # events table grows (append-only, no dedup) but the incident stays
    # a single row since incident_id_for() is deterministic per alert.
    with AuditStore(db_path) as audit:
        audit.append(_record())  # first "watch --once" run

    with IncidentStore(db_path) as incidents:
        first_sync = incidents.sync()
        [incident_after_first] = incidents.list()

    with AuditStore(db_path) as audit:
        audit.append(_record())  # second "watch --once" run, same alert

    with IncidentStore(db_path) as incidents:
        second_sync = incidents.sync()
        all_incidents = incidents.list()

    assert first_sync == 1
    assert second_sync == 0  # same incident_id already exists, no new row
    assert len(all_incidents) == 1
    assert all_incidents[0].incident_id == incident_after_first.incident_id


def test_verify_unaffected_by_incident_status_mutation(db_path):
    # Proves status mutation doesn't touch the chained events table.
    with AuditStore(db_path) as audit:
        audit.append(_record())
        audit.append(_record(step_index=1, rule="skipped_test"))

    with IncidentStore(db_path) as incidents:
        [first, _second] = incidents.list()
        incidents.acknowledge(first.incident_id, note="reviewed")
        incidents.resolve(first.incident_id)

    with AuditStore(db_path) as audit:
        assert audit.verify() is None
