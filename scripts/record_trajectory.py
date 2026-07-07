#!/usr/bin/env python3
"""Convert JSONL tool-call logs into AgentBench trajectory JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load steps from a JSONL file, skipping blank lines and comments."""
    steps: list[dict[str, Any]] = []

    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_no}: each line must be a JSON object")
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


def record_trajectory(
    input_path: Path,
    output_path: Path,
    *,
    agent: str | None = None,
    model: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Read JSONL tool calls and write AgentBench trajectory JSON."""
    steps = load_jsonl(input_path)

    metadata: dict[str, Any] = {"source": source or str(input_path)}
    if agent:
        metadata["agent"] = agent
    if model:
        metadata["model"] = model

    trajectory = build_trajectory(steps, metadata)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(trajectory, indent=2) + "\n", encoding="utf-8")
    return trajectory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert JSONL tool-call logs to AgentBench trajectory JSON",
    )
    parser.add_argument("input", type=Path, help="Input JSONL file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output trajectory JSON path",
    )
    parser.add_argument("--agent", help="Agent name for trajectory metadata")
    parser.add_argument("--model", help="Model name for trajectory metadata")
    parser.add_argument("--source", help="Source label for trajectory metadata")
    args = parser.parse_args(argv)

    try:
        trajectory = record_trajectory(
            args.input,
            args.output,
            agent=args.agent,
            model=args.model,
            source=args.source,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(trajectory['steps'])} steps to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
