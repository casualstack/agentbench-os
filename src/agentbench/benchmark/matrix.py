"""Run eval tasks across a model × prompt matrix and detect score drift."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from agentbench.gate.evaluator import Evaluator
from agentbench.models.task import RunResult


class MatrixCell(BaseModel):
    """One model/prompt combination mapped to a recorded trajectory."""

    model: str
    prompt: str
    trajectory: Path

    @field_validator("trajectory", mode="before")
    @classmethod
    def _coerce_path(cls, value: str | Path) -> Path:
        return Path(value)

    @property
    def key(self) -> str:
        return f"{self.model}/{self.prompt}"


class BaselineScores(BaseModel):
    """Expected pass rates for drift comparison."""

    overall_pass_rate: float | None = None
    by_model: dict[str, float] = Field(default_factory=dict)
    by_prompt: dict[str, float] = Field(default_factory=dict)
    cells: dict[str, float] = Field(default_factory=dict)


class MatrixConfig(BaseModel):
    """YAML/JSON-driven benchmark matrix configuration."""

    name: str = "matrix"
    tasks_dir: Path = Path("tasks")
    task_files: list[str] | None = None
    task_subset: Path | None = None
    cells: list[MatrixCell] = Field(default_factory=list)
    baseline: BaselineScores | None = None
    drift_threshold: float = 0.05

    @field_validator("tasks_dir", mode="before")
    @classmethod
    def _coerce_tasks_dir(cls, value: str | Path) -> Path:
        return Path(value)

    @field_validator("task_subset", mode="before")
    @classmethod
    def _coerce_task_subset(cls, value: str | Path | None) -> Path | None:
        if value is None:
            return None
        return Path(value)

    @classmethod
    def _normalize_raw(cls, data: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(data)
        if "runs" in normalized and "cells" not in normalized:
            normalized["cells"] = normalized.pop("runs")
        return normalized

    @classmethod
    def from_file(cls, path: Path | str) -> MatrixConfig:
        path = Path(path)
        with path.open(encoding="utf-8") as handle:
            if path.suffix.lower() in {".yaml", ".yml"}:
                data = yaml.safe_load(handle)
            else:
                data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: matrix config must be a mapping")
        return cls.model_validate(cls._normalize_raw(data))

    @classmethod
    def from_yaml(cls, path: Path | str) -> MatrixConfig:
        return cls.from_file(path)

    def resolve_task_files(self) -> list[Path]:
        """Return task JSON paths included in this matrix run."""
        if self.task_files:
            return [self.tasks_dir / name for name in self.task_files]

        if self.task_subset is not None:
            from agentbench.gate.manifest import load_task_manifest

            names = load_task_manifest(self.task_subset)
            return [self.tasks_dir / name for name in names]

        return sorted(
            path
            for path in self.tasks_dir.glob("*.json")
            if path.name != "manifest_pass.json"
        )


class CellResult(BaseModel):
    """Pass rate for one matrix cell across selected tasks."""

    model: str
    prompt: str
    trajectory: Path
    tasks_total: int
    tasks_passed: int
    pass_rate: float
    task_results: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.model}/{self.prompt}"

    @property
    def total(self) -> int:
        return self.tasks_total

    @property
    def passed(self) -> int:
        return self.tasks_passed


class MatrixResult(BaseModel):
    """Aggregate outcome of a full matrix run."""

    name: str
    cells: list[CellResult]
    overall_pass_rate: float
    by_model: dict[str, float]
    by_prompt: dict[str, float]

    def summary(self) -> str:
        lines = [
            f"Matrix: {self.name}",
            f"Overall pass rate: {self.overall_pass_rate:.1%}",
            "",
            "Cells:",
        ]
        for cell in self.cells:
            lines.append(
                f"  {cell.key}: {cell.tasks_passed}/{cell.tasks_total} "
                f"({cell.pass_rate:.1%})"
            )
        if self.by_model:
            lines.append("")
            lines.append("By model:")
            for model, rate in sorted(self.by_model.items()):
                lines.append(f"  {model}: {rate:.1%}")
        if self.by_prompt:
            lines.append("")
            lines.append("By prompt:")
            for prompt, rate in sorted(self.by_prompt.items()):
                lines.append(f"  {prompt}: {rate:.1%}")
        return "\n".join(lines)

    def to_table(self, *, format: str = "markdown") -> str:
        """Render matrix pass rates as a table."""
        if format != "markdown":
            raise ValueError(f"unsupported table format: {format!r}")

        lines = [
            "| Model | Prompt | Pass rate |",
            "| --- | --- | --- |",
        ]
        for cell in self.cells:
            lines.append(
                f"| {cell.model} | {cell.prompt} | {cell.pass_rate:.1%} |"
            )
        return "\n".join(lines)

    def detect_drift(
        self,
        baseline: MatrixResult,
        *,
        threshold: float = 0.05,
    ) -> list[str]:
        """Compare cell pass rates to a baseline matrix run."""
        warnings: list[str] = []
        baseline_by_key = {(cell.model, cell.prompt): cell for cell in baseline.cells}

        for cell in self.cells:
            base = baseline_by_key.get((cell.model, cell.prompt))
            if base is None:
                continue
            delta = abs(cell.pass_rate - base.pass_rate)
            if delta > threshold:
                warnings.append(
                    f"{cell.model}/{cell.prompt}: "
                    f"{base.pass_rate:.1%} -> {cell.pass_rate:.1%} "
                    f"(delta {delta:.1%})"
                )
        return warnings


class DriftFinding(BaseModel):
    """A single baseline vs current score delta that exceeds threshold."""

    scope: str
    key: str
    baseline: float
    current: float
    delta: float


class DriftReport(BaseModel):
    """Score drift analysis against a baseline."""

    threshold: float
    drift_detected: bool
    findings: list[DriftFinding] = Field(default_factory=list)

    def summary(self) -> str:
        if not self.drift_detected:
            return f"No score drift detected (threshold={self.threshold:.1%})"
        lines = [f"Score drift detected (threshold={self.threshold:.1%}):"]
        for finding in self.findings:
            lines.append(
                f"  {finding.scope} {finding.key}: "
                f"{finding.baseline:.1%} -> {finding.current:.1%} "
                f"(delta {finding.delta:+.1%})"
            )
        return "\n".join(lines)


def _aggregate_rates(cells: list[CellResult], field: str) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for cell in cells:
        key = getattr(cell, field)
        buckets.setdefault(key, []).append(cell.pass_rate)
    return {key: sum(rates) / len(rates) for key, rates in buckets.items()}


def detect_score_drift(
    result: MatrixResult,
    baseline: BaselineScores,
    *,
    threshold: float,
) -> DriftReport:
    """Compare matrix pass rates to baseline and flag deltas above threshold."""
    findings: list[DriftFinding] = []

    def _check(scope: str, key: str, baseline_rate: float, current_rate: float) -> None:
        delta = current_rate - baseline_rate
        if abs(delta) > threshold:
            findings.append(
                DriftFinding(
                    scope=scope,
                    key=key,
                    baseline=baseline_rate,
                    current=current_rate,
                    delta=delta,
                )
            )

    if baseline.overall_pass_rate is not None:
        _check("overall", "pass_rate", baseline.overall_pass_rate, result.overall_pass_rate)

    for model, rate in baseline.by_model.items():
        current = result.by_model.get(model)
        if current is not None:
            _check("model", model, rate, current)

    for prompt, rate in baseline.by_prompt.items():
        current = result.by_prompt.get(prompt)
        if current is not None:
            _check("prompt", prompt, rate, current)

    current_cells = {cell.key: cell.pass_rate for cell in result.cells}
    for key, rate in baseline.cells.items():
        current = current_cells.get(key)
        if current is not None:
            _check("cell", key, rate, current)

    return DriftReport(
        threshold=threshold,
        drift_detected=bool(findings),
        findings=findings,
    )


class MatrixRunner:
    """Execute a configured model × prompt matrix using recorded trajectories."""

    def __init__(self, evaluator: Evaluator | None = None) -> None:
        self._evaluator = evaluator or Evaluator()

    def run(
        self,
        config: MatrixConfig | None = None,
        *,
        tasks_dir: Path | str | None = None,
        config_path: Path | str | None = None,
    ) -> MatrixResult:
        if config is None and config_path is None:
            raise ValueError("config or config_path is required")

        if config_path is not None:
            config = MatrixConfig.from_file(config_path)
        assert config is not None

        if tasks_dir is not None:
            config = config.model_copy(update={"tasks_dir": Path(tasks_dir)})

        return self._run_config(config)

    def _run_config(self, config: MatrixConfig) -> MatrixResult:
        task_files = config.resolve_task_files()
        if not task_files:
            raise ValueError(f"No task files found under {config.tasks_dir}")

        cell_results: list[CellResult] = []

        for cell in config.cells:
            passed = 0
            task_results: list[dict[str, Any]] = []

            for task_file in task_files:
                run_result = self._evaluator.evaluate_files(task_file, cell.trajectory)
                if run_result.passed:
                    passed += 1
                task_results.append(_serialize_run_result(run_result))

            total = len(task_files)
            cell_results.append(
                CellResult(
                    model=cell.model,
                    prompt=cell.prompt,
                    trajectory=cell.trajectory,
                    tasks_total=total,
                    tasks_passed=passed,
                    pass_rate=passed / total if total else 0.0,
                    task_results=task_results,
                )
            )

        total_tasks = sum(cell.tasks_total for cell in cell_results)
        total_passed = sum(cell.tasks_passed for cell in cell_results)
        overall = total_passed / total_tasks if total_tasks else 0.0

        return MatrixResult(
            name=config.name,
            cells=cell_results,
            overall_pass_rate=overall,
            by_model=_aggregate_rates(cell_results, "model"),
            by_prompt=_aggregate_rates(cell_results, "prompt"),
        )

    def run_yaml(self, path: Path | str) -> MatrixResult:
        return self.run(config_path=path)

    def write_result(self, result: MatrixResult, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )


def _serialize_run_result(result: RunResult) -> dict[str, Any]:
    return {
        "task_id": result.task_id,
        "passed": result.passed,
        "failures": [
            {
                "oracle_type": failure.oracle_type,
                "message": failure.message,
            }
            for failure in result.failures
        ],
    }
