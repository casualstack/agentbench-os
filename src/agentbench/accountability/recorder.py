"""Convert JSONL tool-call logs into AgentBench trajectory documents."""

from __future__ import annotations

import json
from typing import Any

# Map common export field names to AgentBench trajectory step shape.
_TOOL_ALIASES = ("tool", "name", "tool_name", "function", "tool_call")
_ARGS_ALIASES = ("args", "arguments", "input", "parameters", "params")
_TYPE_ALIASES = ("type", "step_type", "kind")


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def normalize_step(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one JSONL record into an AgentBench trajectory step."""
    tool = _first_present(raw, _TOOL_ALIASES)
    args = _first_present(raw, _ARGS_ALIASES)
    step_type = _first_present(raw, _TYPE_ALIASES) or "tool_call"

    if not isinstance(args, dict):
        args = {}

    step: dict[str, Any] = {
        "type": str(step_type),
        "tool": str(tool) if tool is not None else None,
        "args": args,
    }

    # Preserve any extra fields for oracle pattern scans (e.g. network checks).
    for key, value in raw.items():
        if key not in (*_TOOL_ALIASES, *_ARGS_ALIASES, *_TYPE_ALIASES):
            step[key] = value

    return step


def steps_from_jsonl(text: str, *, source: str = "<jsonl>") -> list[dict[str, Any]]:
    """Parse JSONL text into normalized steps, skipping blanks and comments."""
    steps: list[dict[str, Any]] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{source}:{line_no}: each line must be a JSON object")
        steps.append(normalize_step(record))

    return steps


def build_trajectory(
    steps: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a trajectory document from normalized steps."""
    return {
        "metadata": metadata or {},
        "steps": steps,
    }
