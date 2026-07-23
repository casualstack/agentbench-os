#!/usr/bin/env python3
"""Convert JSONL tool-call logs into AgentBench trajectory JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from agentbench.accountability.recorder import build_trajectory, steps_from_jsonl
except ImportError:  # pragma: no cover
    sys.exit("agentbench is not installed — run: pip install -e .")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load steps from a JSONL file, skipping blank lines and comments."""
    return steps_from_jsonl(path.read_text(encoding="utf-8"), source=str(path))


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
