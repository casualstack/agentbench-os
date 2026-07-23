"""Generate git-like trajectory diff reports for CI accountability."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from agentbench.core.trajectory import Trajectory


@dataclass
class DiffReport:
    """Human-readable and machine-readable trajectory comparison."""

    baseline_path: str
    candidate_path: str
    baseline_steps: int
    candidate_steps: int
    added_tools: dict[str, int]
    removed_tools: dict[str, int]
    added_files: list[str]
    removed_files: list[str]
    added_commands: list[str]
    removed_commands: list[str]

    @property
    def changed(self) -> bool:
        return any(
            (
                self.added_tools,
                self.removed_tools,
                self.added_files,
                self.removed_files,
                self.added_commands,
                self.removed_commands,
                self.baseline_steps != self.candidate_steps,
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "changed": self.changed,
            "baseline_path": self.baseline_path,
            "candidate_path": self.candidate_path,
            "baseline_steps": self.baseline_steps,
            "candidate_steps": self.candidate_steps,
            "step_delta": self.candidate_steps - self.baseline_steps,
            "added_tools": self.added_tools,
            "removed_tools": self.removed_tools,
            "added_files": self.added_files,
            "removed_files": self.removed_files,
            "added_commands": self.added_commands,
            "removed_commands": self.removed_commands,
        }

    def to_markdown(self) -> str:
        lines = [
            "# AgentBench /diff Report",
            "",
            f"- Baseline: `{self.baseline_path}`",
            f"- Candidate: `{self.candidate_path}`",
            f"- Steps: `{self.baseline_steps} -> {self.candidate_steps}` "
            f"(delta `{self.candidate_steps - self.baseline_steps:+d}`)",
            f"- Changed: `{self.changed}`",
            "",
        ]
        lines.extend(_section("Tool usage added", self.added_tools))
        lines.extend(_section("Tool usage removed", self.removed_tools))
        lines.extend(_list_section("Files newly touched", self.added_files))
        lines.extend(_list_section("Files no longer touched", self.removed_files))
        lines.extend(_list_section("New commands", self.added_commands))
        lines.extend(_list_section("Commands removed", self.removed_commands))
        return "\n".join(lines).rstrip() + "\n"


def build_diff_report(
    baseline_path: Path | str,
    candidate_path: Path | str,
) -> DiffReport:
    baseline_path = Path(baseline_path)
    candidate_path = Path(candidate_path)
    baseline = Trajectory.from_file(baseline_path)
    candidate = Trajectory.from_file(candidate_path)

    baseline_tools = Counter(step.tool for step in baseline.steps if step.tool)
    candidate_tools = Counter(step.tool for step in candidate.steps if step.tool)

    return DiffReport(
        baseline_path=str(baseline_path),
        candidate_path=str(candidate_path),
        baseline_steps=len(baseline.steps),
        candidate_steps=len(candidate.steps),
        added_tools=dict(sorted((candidate_tools - baseline_tools).items())),
        removed_tools=dict(sorted((baseline_tools - candidate_tools).items())),
        added_files=_sorted_unique(_edited_files(candidate) - _edited_files(baseline)),
        removed_files=_sorted_unique(_edited_files(baseline) - _edited_files(candidate)),
        added_commands=_sorted_unique(_commands(candidate) - _commands(baseline)),
        removed_commands=_sorted_unique(_commands(baseline) - _commands(candidate)),
    )


def _edited_files(trajectory: Trajectory) -> set[str]:
    return {path for _, path, _ in trajectory.file_edits()}


def _commands(trajectory: Trajectory) -> set[str]:
    return {cmd.strip() for _, cmd in trajectory.commands() if cmd.strip()}


def _sorted_unique(items: set[str]) -> list[str]:
    return sorted(items, key=lambda value: value.lower())


def _section(title: str, counts: dict[str, int]) -> list[str]:
    lines = [f"## {title}"]
    if not counts:
        lines.append("- none")
    else:
        for key, value in counts.items():
            lines.append(f"- `{key}` x{value}")
    lines.append("")
    return lines


def _list_section(title: str, items: list[str]) -> list[str]:
    lines = [f"## {title}"]
    if not items:
        lines.append("- none")
    else:
        for item in items:
            lines.append(f"- `{item}`")
    lines.append("")
    return lines
