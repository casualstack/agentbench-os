"""Tests for CLI entrypoints."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agentbench.accountability.audit import AuditStore, IncidentStore
from agentbench.cli.main import main


def test_cli_run_pass_exit_code(tasks_dir: Path, fixtures_dir: Path):
    code = main(
        [
            "run",
            "--task",
            str(tasks_dir / "01_fix_failing_test_no_delete.json"),
            "--trajectory",
            str(fixtures_dir / "trajectory_pass.json"),
        ]
    )
    assert code == 0


def test_cli_run_fail_exit_code(tasks_dir: Path, fixtures_dir: Path):
    code = main(
        [
            "run",
            "--task",
            str(tasks_dir / "01_fix_failing_test_no_delete.json"),
            "--trajectory",
            str(fixtures_dir / "trajectory_regression.json"),
        ]
    )
    assert code == 1


def test_cli_gate_runs_task_directory(tasks_dir: Path, fixtures_dir: Path):
    code = main(
        [
            "gate",
            "--tasks",
            str(tasks_dir),
            "--trajectory",
            str(fixtures_dir / "trajectory_pass.json"),
        ]
    )
    assert code in (0, 1)


def test_cli_diff_detects_changes(fixtures_dir: Path, tmp_path: Path):
    report = tmp_path / "diff-report.md"
    code = main(
        [
            "diff",
            "--baseline",
            str(fixtures_dir / "trajectory_pass.json"),
            "--candidate",
            str(fixtures_dir / "trajectory_regression.json"),
            "--output",
            str(report),
            "--fail-on-change",
        ]
    )
    assert code == 1
    text = report.read_text(encoding="utf-8")
    assert "/diff Report" in text
    assert "Changed: `True`" in text


def _audit_record(**overrides):
    record = {
        "ts": "2026-07-15T00:00:00Z",
        "agent": "claude-code",
        "session_id": "s1",
        "cwd": None,
        "model": None,
        "step_index": 0,
        "rule": "deleted_assertion",
        "severity": "critical",
        "title": "Deleted a test assertion",
        "detail": "detail",
        "path": None,
        "source_path": None,
        "source_size": None,
        "source_mtime": None,
    }
    record.update(overrides)
    return record


def test_cli_audit_verify_ok_on_untouched_db(tmp_path: Path):
    db_path = tmp_path / "audit.db"
    with AuditStore(db_path) as store:
        store.append(_audit_record())

    code = main(["audit", "verify", "--db", str(db_path)])
    assert code == 0


def test_cli_audit_verify_ok_on_missing_db(tmp_path: Path):
    # A store that doesn't exist yet is an empty, trivially intact chain.
    code = main(["audit", "verify", "--db", str(tmp_path / "audit.db")])
    assert code == 0


def test_cli_audit_verify_reports_broken_chain(tmp_path: Path):
    db_path = tmp_path / "audit.db"
    with AuditStore(db_path) as store:
        store.append(_audit_record())
        store.append(_audit_record(rule="skipped_test"))

    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE events SET detail = 'edited' WHERE id = 1")
    conn.commit()
    conn.close()

    code = main(["audit", "verify", "--db", str(db_path)])
    assert code == 1


def test_cli_incidents_list_shows_synced_incident(tmp_path: Path, capsys):
    db_path = tmp_path / "audit.db"
    with AuditStore(db_path) as store:
        store.append(_audit_record())

    code = main(["incidents", "list", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Deleted a test assertion" in out
    assert "[open]" in out


def test_cli_incidents_list_empty_db(tmp_path: Path, capsys):
    code = main(["incidents", "list", "--db", str(tmp_path / "audit.db")])
    out = capsys.readouterr().out
    assert code == 0
    assert "No incidents found" in out


def test_cli_incidents_show_ack_resolve_round_trip(tmp_path: Path, capsys):
    db_path = tmp_path / "audit.db"
    with AuditStore(db_path) as store:
        store.append(_audit_record())
    with IncidentStore(db_path) as incidents:
        [incident] = incidents.list()
        incident_id = incident.incident_id

    show_code = main(["incidents", "show", incident_id, "--db", str(db_path)])
    show_out = capsys.readouterr().out
    assert show_code == 0
    assert incident_id in show_out
    assert "[open]" in show_out

    ack_code = main(
        ["incidents", "ack", incident_id, "--note", "reviewed", "--db", str(db_path)]
    )
    capsys.readouterr()
    assert ack_code == 0

    show_after_ack = main(["incidents", "show", incident_id, "--db", str(db_path)])
    show_after_ack_out = capsys.readouterr().out
    assert show_after_ack == 0
    assert "[acknowledged]" in show_after_ack_out
    assert "reviewed" in show_after_ack_out

    resolve_code = main(["incidents", "resolve", incident_id, "--db", str(db_path)])
    capsys.readouterr()
    assert resolve_code == 0

    show_after_resolve = main(["incidents", "show", incident_id, "--db", str(db_path)])
    show_after_resolve_out = capsys.readouterr().out
    assert show_after_resolve == 0
    assert "[resolved]" in show_after_resolve_out
    assert "Resolved:" in show_after_resolve_out

    # Status mutation must never touch the chained events table.
    verify_code = main(["audit", "verify", "--db", str(db_path)])
    assert verify_code == 0


def test_cli_incidents_show_unknown_id(tmp_path: Path, capsys):
    code = main(["incidents", "show", "doesnotexist", "--db", str(tmp_path / "audit.db")])
    out = capsys.readouterr().out
    assert code == 1
    assert "No incident found" in out


def test_cli_incidents_list_filters_by_status(tmp_path: Path, capsys):
    db_path = tmp_path / "audit.db"
    with AuditStore(db_path) as store:
        store.append(_audit_record(step_index=0))
        store.append(_audit_record(step_index=1, rule="skipped_test"))
    with IncidentStore(db_path) as incidents:
        [first, _second] = incidents.list()
        incidents.resolve(first.incident_id)

    code = main(["incidents", "list", "--status", "open", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "1 incident(s)" in out
