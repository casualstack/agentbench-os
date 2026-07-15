"""Tests for the historical audit export (sessions_from_incidents + digest)."""

from __future__ import annotations

import json

import pytest

from agentbench.accountability.audit.export import sessions_from_incidents
from agentbench.accountability.audit.incidents import IncidentStore
from agentbench.accountability.audit.store import AuditStore
from agentbench.accountability.digest import render_digest


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


def test_sessions_from_incidents_groups_by_session(db_path):
    with AuditStore(db_path) as audit:
        audit.append(_record(session_id="s1", step_index=0))
        audit.append(_record(session_id="s1", step_index=1, rule="skipped_test"))
        audit.append(_record(session_id="s2", step_index=0, rule="hook_bypass"))

    with IncidentStore(db_path) as incidents:
        sessions = sessions_from_incidents(incidents.list())

    assert len(sessions) == 2
    s1 = next(s for s in sessions if s["session_id"] == "s1")
    s2 = next(s for s in sessions if s["session_id"] == "s2")
    assert len(s1["alerts"]) == 2
    assert len(s2["alerts"]) == 1
    assert "steps" not in s1  # no live step count to report from history


def test_sessions_from_incidents_carries_status(db_path):
    with AuditStore(db_path) as audit:
        audit.append(_record())

    with IncidentStore(db_path) as incidents:
        [incident] = incidents.list()
        incidents.resolve(incident.incident_id, note="fixed")
        sessions = sessions_from_incidents(incidents.list())

    assert sessions[0]["alerts"][0]["status"] == "resolved"


def test_render_digest_shows_status_when_present(db_path):
    with AuditStore(db_path) as audit:
        audit.append(_record())

    with IncidentStore(db_path) as incidents:
        [incident] = incidents.list()
        incidents.acknowledge(incident.incident_id)
        sessions = sessions_from_incidents(incidents.list())

    markdown = render_digest(sessions)
    assert "status: acknowledged" in markdown
    assert "Steps:" not in markdown  # omitted for historical export


def test_render_digest_watch_snapshot_unaffected_by_status_support():
    # Live watch session dicts never carry "status" -- must render exactly
    # as before (regression guard on the digest.py change for task 8).
    sessions = [
        {
            "agent": "claude-code",
            "session_id": "abcdef12",
            "cwd": "C:\\work\\myrepo",
            "model": "claude-x",
            "steps": 5,
            "alerts": [
                {
                    "rule": "deleted_assertion",
                    "severity": "critical",
                    "title": "Deleted a test assertion",
                    "detail": "detail text",
                    "step_index": 0,
                    "path": "tests/test_calc.py",
                }
            ],
        }
    ]
    markdown = render_digest(sessions)
    assert "Steps: 5" in markdown
    assert "status:" not in markdown


def test_audit_export_md_via_cli(tmp_path):
    from agentbench.cli.main import main

    db_path = tmp_path / "audit.db"
    output = tmp_path / "export.md"
    with AuditStore(db_path) as audit:
        audit.append(_record())

    code = main(
        ["audit", "export", "--output", str(output), "--db", str(db_path)]
    )
    assert code == 0
    text = output.read_text(encoding="utf-8")
    assert "AgentBench Session Digest" in text
    assert "Deleted a test assertion" in text
    assert "status: open" in text


def test_audit_export_json_via_cli(tmp_path):
    from agentbench.cli.main import main

    db_path = tmp_path / "audit.db"
    output = tmp_path / "export.json"
    with AuditStore(db_path) as audit:
        audit.append(_record())
        audit.append(_record(step_index=1, rule="skipped_test"))

    code = main(
        [
            "audit",
            "export",
            "--output",
            str(output),
            "--format",
            "json",
            "--db",
            str(db_path),
        ]
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["incident_count"] == 2
    assert len(payload["incidents"]) == 2
    assert payload["incidents"][0]["status"] == "open"


def test_audit_export_filters_by_project(tmp_path):
    from agentbench.cli.main import main

    db_path = tmp_path / "audit.db"
    output = tmp_path / "export.md"
    with AuditStore(db_path) as audit:
        audit.append(_record(cwd="C:\\work\\repo-a"))
        audit.append(_record(step_index=1, cwd="C:\\work\\repo-b", rule="skipped_test"))

    code = main(
        [
            "audit",
            "export",
            "--output",
            str(output),
            "--project",
            "C:\\work\\repo-a",
            "--db",
            str(db_path),
        ]
    )
    assert code == 0
    text = output.read_text(encoding="utf-8")
    assert "repo-a" in text
    assert "repo-b" not in text


def test_audit_export_filters_by_since(tmp_path):
    from agentbench.cli.main import main

    db_path = tmp_path / "audit.db"
    output = tmp_path / "export.json"
    with AuditStore(db_path) as audit:
        audit.append(_record(ts="2026-07-15T00:00:00Z"))
        audit.append(_record(step_index=1, ts="2026-07-16T00:00:00Z", rule="skipped_test"))

    code = main(
        [
            "audit",
            "export",
            "--output",
            str(output),
            "--format",
            "json",
            "--since",
            "2026-07-16T00:00:00Z",
            "--db",
            str(db_path),
        ]
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["incident_count"] == 1
    assert payload["incidents"][0]["rule"] == "skipped_test"
