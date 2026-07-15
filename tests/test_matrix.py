"""Tests for the model matrix runner (expected interface)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentbench.cli.main import main
from agentbench.eval.matrix import MatrixResult, MatrixRunner


@pytest.fixture
def matrix_config(fixtures_dir: Path, tmp_path: Path) -> Path:
    """Minimal 2-cell config pointing at shipped trajectory fixtures."""
    config = {
        "task_files": ["01_fix_failing_test_no_delete.json"],
        "runs": [
            {
                "model": "claude-sonnet",
                "prompt": "default",
                "trajectory": str(fixtures_dir / "trajectory_pass.json"),
            },
            {
                "model": "claude-sonnet",
                "prompt": "strict",
                "trajectory": str(fixtures_dir / "trajectory_regression.json"),
            },
        ],
        "drift_threshold": 0.15,
    }
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def test_matrix_runner_returns_result_with_cells(tasks_dir: Path, matrix_config: Path):
    runner = MatrixRunner()
    result = runner.run(tasks_dir=tasks_dir, config_path=matrix_config)

    assert isinstance(result, MatrixResult)
    assert len(result.cells) == 2
    labels = {(c.model, c.prompt) for c in result.cells}
    assert ("claude-sonnet", "default") in labels
    assert ("claude-sonnet", "strict") in labels


def test_matrix_pass_rates_between_zero_and_one(tasks_dir: Path, matrix_config: Path):
    result = MatrixRunner().run(tasks_dir=tasks_dir, config_path=matrix_config)

    for cell in result.cells:
        assert 0 <= cell.pass_rate <= 1.0
        assert cell.total >= 1
        assert 0 <= cell.passed <= cell.total


def test_matrix_default_cell_passes_regression_cell_fails(tasks_dir: Path, matrix_config: Path):
    result = MatrixRunner().run(tasks_dir=tasks_dir, config_path=matrix_config)
    by_key = {(c.model, c.prompt): c for c in result.cells}

    default = by_key[("claude-sonnet", "default")]
    strict = by_key[("claude-sonnet", "strict")]

    assert default.pass_rate >= strict.pass_rate
    assert strict.passed < strict.total


def test_matrix_to_table_markdown(tasks_dir: Path, matrix_config: Path):
    result = MatrixRunner().run(tasks_dir=tasks_dir, config_path=matrix_config)
    table = result.to_table(format="markdown")

    assert "Model" in table
    assert "pass rate" in table.lower()
    assert "claude-sonnet" in table


def test_matrix_detect_drift(tasks_dir: Path, matrix_config: Path, fixtures_dir: Path, tmp_path: Path):
    runner = MatrixRunner()
    baseline = runner.run(tasks_dir=tasks_dir, config_path=matrix_config)

    drift_config = tmp_path / "drift.json"
    drift_config.write_text(
        json.dumps(
            {
                "task_files": ["01_fix_failing_test_no_delete.json"],
                "runs": [
                    {
                        "model": "claude-sonnet",
                        "prompt": "default",
                        "trajectory": str(fixtures_dir / "trajectory_regression.json"),
                    },
                    {
                        "model": "claude-sonnet",
                        "prompt": "strict",
                        "trajectory": str(fixtures_dir / "trajectory_regression.json"),
                    },
                ],
                "drift_threshold": 0.01,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    current = runner.run(tasks_dir=tasks_dir, config_path=drift_config)
    warnings = current.detect_drift(baseline, threshold=0.01)

    assert isinstance(warnings, list)


def test_matrix_cli_exit_code(tasks_dir: Path, matrix_config: Path):
    code = main(
        [
            "matrix",
            "--config",
            str(matrix_config),
            "--tasks",
            str(tasks_dir),
            "--output",
            "markdown",
        ]
    )
    assert code in (0, 1)
