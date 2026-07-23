"""Orchestrate agent runs — MVP applies recorded trajectories to a workspace."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from agentbench.eval.models import EvalTask
from agentbench.core.trajectory import Trajectory, normalize_rel_path


class AgentRunner:
    """Apply a recorded trajectory to a task workspace (MVP stub)."""

    def __init__(self, task: EvalTask, trajectory: Trajectory):
        self.task = task
        self.trajectory = trajectory
        self._workspace_dir: tempfile.TemporaryDirectory[str] | None = None
        self._workspace_path: Path | None = None

    def setup_workspace(self) -> Path:
        """Create temp workspace with initial task files."""
        self._workspace_dir = tempfile.TemporaryDirectory(prefix="agentbench_")
        workspace = Path(self._workspace_dir.name)

        for rel_path, content in self.task.workspace.items():
            file_path = workspace / normalize_rel_path(rel_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        self._workspace_path = workspace
        return workspace

    def apply_trajectory(self, workspace: Path | None = None) -> Path:
        """Replay file edits from trajectory onto workspace."""
        ws = workspace or self._workspace_path
        if ws is None:
            ws = self.setup_workspace()

        for _step_idx, path, content in self.trajectory.file_edits():
            file_path = ws / normalize_rel_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        return ws

    def run(self) -> Path:
        """Setup workspace and apply trajectory; return final workspace path."""
        workspace = self.setup_workspace()
        return self.apply_trajectory(workspace)

    def cleanup(self) -> None:
        if self._workspace_dir is not None:
            self._workspace_dir.cleanup()
            self._workspace_dir = None
            self._workspace_path = None

    def __enter__(self) -> Path:
        return self.run()

    def __exit__(self, *args: object) -> None:
        self.cleanup()
