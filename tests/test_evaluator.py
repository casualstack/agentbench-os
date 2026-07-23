"""Integration tests for the gate evaluator."""

from __future__ import annotations

from pathlib import Path

from agentbench.eval.gate.evaluator import Evaluator
from agentbench.eval.models import EvalTask


def test_evaluator_passes_good_trajectory(tasks_dir: Path, trajectory_pass):
    task = EvalTask.from_file(tasks_dir / "01_fix_failing_test_no_delete.json")
    result = Evaluator().evaluate(task, trajectory_pass)
    assert result.passed


def test_evaluator_fails_regression_trajectory(tasks_dir: Path, trajectory_regression):
    task = EvalTask.from_file(tasks_dir / "01_fix_failing_test_no_delete.json")
    result = Evaluator().evaluate(task, trajectory_regression)
    assert not result.passed
    assert len(result.failures) >= 1


def test_evaluator_fails_network_trajectory(tasks_dir: Path, trajectory_network):
    task = EvalTask.from_file(tasks_dir / "03_offline_fix_no_network.json")
    result = Evaluator().evaluate(task, trajectory_network)
    assert not result.passed
    assert any(r.oracle_type == "no_network" for r in result.failures)


def test_evaluate_directory_runs_all_tasks(tasks_dir: Path, trajectory_pass, fixtures_dir: Path):
    results = Evaluator().evaluate_directory(tasks_dir, fixtures_dir / "trajectory_pass.json")
    task_files = [p for p in tasks_dir.glob("*.json") if p.name != "manifest_pass.json"]
    assert len(results) == len(task_files)
