"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TASKS_DIR = Path(__file__).parent.parent / "tasks"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def tasks_dir() -> Path:
    return TASKS_DIR


@pytest.fixture
def trajectory_pass(fixtures_dir: Path):
    from agentbench.core.trajectory import Trajectory

    return Trajectory.from_file(fixtures_dir / "trajectory_pass.json")


@pytest.fixture
def trajectory_regression(fixtures_dir: Path):
    from agentbench.core.trajectory import Trajectory

    return Trajectory.from_file(fixtures_dir / "trajectory_regression.json")


@pytest.fixture
def trajectory_network(fixtures_dir: Path):
    from agentbench.core.trajectory import Trajectory

    return Trajectory.from_file(fixtures_dir / "trajectory_network.json")
