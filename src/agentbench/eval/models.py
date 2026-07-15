"""Core data models for eval tasks, oracles, and run results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Oracle:
    """A property-based check applied after an agent run."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Oracle:
        oracle_type = data.get("type")
        if not oracle_type:
            raise ValueError("Oracle must have a 'type' field")
        params = {k: v for k, v in data.items() if k != "type"}
        return cls(type=oracle_type, params=params)


@dataclass
class EvalTask:
    """An eval task: prompt, initial workspace, and oracles."""

    id: str
    name: str
    description: str
    prompt: str
    workspace: dict[str, str]
    oracles: list[Oracle]
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalTask:
        from agentbench.eval.dsl.validator import validate_task_dict

        validate_task_dict(data)

        oracles = [Oracle.from_dict(o) for o in data["oracles"]]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            prompt=data["prompt"],
            workspace=dict(data["workspace"]),
            oracles=oracles,
            tags=list(data.get("tags", [])),
        )

    @classmethod
    def from_file(cls, path: Path | str) -> EvalTask:
        path = Path(path)
        with path.open(encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


@dataclass
class OracleResult:
    """Outcome of a single oracle check."""

    oracle_type: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """Aggregate outcome of running all oracles for a task."""

    task_id: str
    passed: bool
    oracle_results: list[OracleResult]
    workspace_path: Path | None = None

    @property
    def failures(self) -> list[OracleResult]:
        return [r for r in self.oracle_results if not r.passed]

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"[{status}] task={self.task_id}"]
        for result in self.oracle_results:
            mark = "ok" if result.passed else "FAIL"
            lines.append(f"  [{mark}] {result.oracle_type}: {result.message}")
        return "\n".join(lines)
