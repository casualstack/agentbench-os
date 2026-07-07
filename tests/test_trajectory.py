"""Tests for trajectory parsing."""

from __future__ import annotations

from agentbench.runner.trajectory import Trajectory


def test_file_edits_extracts_write_operations(trajectory_pass):
    edits = trajectory_pass.file_edits()
    assert len(edits) == 1
    assert edits[0][1] == "src/calc.py"
    assert "return a + b" in edits[0][2]


def test_touched_file_detects_modifications(trajectory_regression):
    assert trajectory_regression.touched_file("tests/test_calc.py")
    assert not trajectory_regression.touched_file("src/calc.py")


def test_commands_extracts_shell_steps(trajectory_pass):
    commands = trajectory_pass.commands()
    assert any("pytest" in cmd for _, cmd in commands)


def test_find_network_violations(trajectory_network):
    violations = trajectory_network.find_network_violations(("curl", "https://"))
    assert len(violations) >= 1
    assert violations[0]["match"] == "curl"
