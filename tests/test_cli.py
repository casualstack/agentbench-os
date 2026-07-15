"""Tests for CLI entrypoints."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agentbench.accountability.audit import AuditStore
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
