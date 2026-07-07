"""Parse and query agent tool-call trajectories from JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def normalize_rel_path(path: str) -> str:
    """Normalize a workspace-relative path to forward slashes."""
    return path.replace("\\", "/").lstrip("/")


@dataclass
class TrajectoryStep:
    """A single step in an agent run (tool call or observation)."""

    step_index: int
    step_type: str
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trajectory:
    """Recorded agent run: sequence of tool calls and metadata."""

    steps: list[TrajectoryStep]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trajectory:
        from agentbench.dsl.validator import validate_trajectory_dict

        validate_trajectory_dict(data)
        steps = []
        for i, step in enumerate(data.get("steps", [])):
            steps.append(
                TrajectoryStep(
                    step_index=i,
                    step_type=step.get("type", "unknown"),
                    tool=step.get("tool"),
                    args=dict(step.get("args", {})),
                    raw=step,
                )
            )
        return cls(steps=steps, metadata=dict(data.get("metadata", {})))

    @classmethod
    def from_file(cls, path: Path | str) -> Trajectory:
        path = Path(path)
        with path.open(encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def file_edits(self) -> list[tuple[int, str, str]]:
        """Return (step_index, path, content) for write/edit operations."""
        edits: list[tuple[int, str, str]] = []
        write_tools = {"write_file", "edit_file", "str_replace", "Write", "StrReplace"}

        for step in self.steps:
            if step.tool in write_tools or step.step_type == "file_edit":
                path = (
                    step.args.get("path")
                    or step.args.get("file_path")
                    or step.args.get("target_file")
                )
                content = step.args.get("content") or step.args.get("new_string", "")
                if path:
                    edits.append((step.step_index, normalize_rel_path(path), content))

        return edits

    def touched_file(self, path: str) -> bool:
        """True if trajectory modified the given file path."""
        normalized = normalize_rel_path(path)
        for _, edit_path, _ in self.file_edits():
            if edit_path == normalized:
                return True
        return False

    def commands(self) -> list[tuple[int, str]]:
        """Return (step_index, command) for shell/run operations."""
        cmds: list[tuple[int, str]] = []
        run_tools = {"run_command", "shell", "bash", "Bash", "execute"}

        for step in self.steps:
            if step.tool in run_tools or step.step_type == "command":
                cmd = step.args.get("command") or step.args.get("cmd", "")
                if cmd:
                    cmds.append((step.step_index, cmd))

        return cmds

    def find_network_violations(self, patterns: tuple[str, ...]) -> list[dict[str, Any]]:
        """Find steps that match network-access patterns."""
        violations: list[dict[str, Any]] = []

        for step in self.steps:
            haystack = json.dumps(step.raw, default=str).lower()
            for pattern in patterns:
                if pattern.lower() in haystack:
                    violations.append(
                        {
                            "step_index": step.step_index,
                            "tool": step.tool,
                            "match": pattern,
                        }
                    )
                    break

        return violations
