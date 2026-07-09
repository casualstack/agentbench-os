"""Tests for CLI entrypoints."""

from __future__ import annotations

from pathlib import Path

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
