"""Unit tests for individual oracles."""

from __future__ import annotations

from pathlib import Path

from agentbench.models.task import Oracle
from agentbench.oracles.assertion_exists import AssertionExistsOracle
from agentbench.oracles.file_not_modified import FileNotModifiedOracle
from agentbench.oracles.no_network import NoNetworkOracle
from agentbench.oracles.test_must_pass import TestMustPassOracle
from agentbench.core.trajectory import Trajectory


def _workspace_with_calc(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    initial = {
        "src/calc.py": "def add(a, b):\n    return a + b\n",
        "tests/test_calc.py": (
            "from src.calc import add\n\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        ),
    }
    for rel, content in initial.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path, initial


def test_assertion_exists_passes_when_pattern_present(trajectory_pass, tmp_path: Path):
    workspace, initial = _workspace_with_calc(tmp_path)
    oracle = Oracle(
        type="assertion_exists",
        params={"path": "tests/test_calc.py", "pattern": r"assert add\(1, 2\) == 3"},
    )
    result = AssertionExistsOracle().check(oracle, workspace, trajectory_pass, initial)
    assert result.passed


def test_assertion_exists_fails_when_pattern_missing(trajectory_regression, tmp_path: Path):
    workspace, initial = _workspace_with_calc(tmp_path)
    (workspace / "tests/test_calc.py").write_text("def test_add():\n    pass\n", encoding="utf-8")
    oracle = Oracle(
        type="assertion_exists",
        params={"path": "tests/test_calc.py", "pattern": r"assert add\(1, 2\) == 3"},
    )
    result = AssertionExistsOracle().check(oracle, workspace, trajectory_regression, initial)
    assert not result.passed


def test_file_not_modified_fails_when_trajectory_edits_file(trajectory_regression, tmp_path: Path):
    workspace, initial = _workspace_with_calc(tmp_path)
    (workspace / "tests/test_calc.py").write_text("def test_add():\n    pass\n", encoding="utf-8")
    oracle = Oracle(type="file_not_modified", params={"path": "tests/test_calc.py"})
    result = FileNotModifiedOracle().check(oracle, workspace, trajectory_regression, initial)
    assert not result.passed


def test_no_network_passes_clean_trajectory(trajectory_pass, tmp_path: Path):
    workspace, initial = _workspace_with_calc(tmp_path)
    oracle = Oracle(type="no_network", params={})
    result = NoNetworkOracle().check(oracle, workspace, trajectory_pass, initial)
    assert result.passed


def test_no_network_fails_on_curl(trajectory_network, tmp_path: Path):
    workspace, initial = _workspace_with_calc(tmp_path)
    oracle = Oracle(type="no_network", params={})
    result = NoNetworkOracle().check(oracle, workspace, trajectory_network, initial)
    assert not result.passed


def test_no_network_fails_on_package_managers(tmp_path: Path):
    workspace, initial = _workspace_with_calc(tmp_path)
    oracle = Oracle(type="no_network", params={})
    commands = (
        "pip install requests",
        "npm install left-pad",
        "npm ci",
        "pnpm add zod",
        "yarn add lodash",
        "bun install",
        "cargo add serde",
        "go get github.com/stretchr/testify",
    )
    for command in commands:
        trajectory = Trajectory.from_dict(
            {
                "steps": [
                    {"type": "tool_call", "tool": "run_command", "args": {"command": command}}
                ]
            }
        )
        result = NoNetworkOracle().check(oracle, workspace, trajectory, initial)
        assert not result.passed, f"expected violation for: {command}"


def test_test_must_pass_runs_pytest(trajectory_pass, tmp_path: Path):
    workspace, initial = _workspace_with_calc(tmp_path)
    oracle = Oracle(
        type="test_must_pass",
        params={"command": "python -m pytest tests/test_calc.py -q", "timeout": 120},
    )
    result = TestMustPassOracle().check(oracle, workspace, trajectory_pass, initial)
    assert result.passed, result.message
