"""Parse Claude Code session JSONL into AgentBench trajectory steps.

A session file is one JSON object per line. Tool calls live in records of
``type: "assistant"`` as ``message.content[]`` blocks of ``type: "tool_use"``.
Every record carries the session ``cwd``; assistant records carry the model.

Tool names are normalized to the canonical AgentBench vocabulary that the
existing oracles already understand (``write_file``, ``str_replace``,
``run_command``); the original name is preserved as ``agent_tool``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

# Claude Code tool name -> canonical AgentBench tool name.
_TOOL_MAP = {
    "Write": "write_file",
    "Edit": "str_replace",
    "MultiEdit": "str_replace",
    "NotebookEdit": "edit_file",
    "Bash": "run_command",
    "PowerShell": "run_command",
    "BashOutput": None,  # observation-only tools carry no side effects
    "Read": None,
    "Glob": None,
    "Grep": None,
    "TodoWrite": None,
    "Task": None,
    "WebFetch": "web_fetch",
    "WebSearch": "web_search",
}


def iter_records(text: str) -> Iterator[dict[str, Any]]:
    """Yield JSON records from session text, skipping blank/corrupt lines.

    Corrupt lines are expected: the last line of a live session file is
    often mid-write when we read it.
    """
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record


def _step_from_tool_use(block: dict[str, Any]) -> dict[str, Any] | None:
    name = block.get("name")
    if not isinstance(name, str):
        return None
    canonical = _TOOL_MAP.get(name, name)
    if canonical is None:
        return None

    args = block.get("input")
    if not isinstance(args, dict):
        args = {}

    return {
        "type": "tool_call",
        "tool": canonical,
        "args": args,
        "agent_tool": name,
    }


def steps_from_records(records: Iterator[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract normalized tool-call steps from parsed session records."""
    steps: list[dict[str, Any]] = []
    for record in records:
        if record.get("type") != "assistant":
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                step = _step_from_tool_use(block)
                if step is not None:
                    steps.append(step)
    return steps


def steps_from_session_text(text: str) -> list[dict[str, Any]]:
    return steps_from_records(iter_records(text))


def session_metadata(records: Iterator[dict[str, Any]]) -> dict[str, Any]:
    """Pull cwd/model/version from session records (first occurrence wins)."""
    metadata: dict[str, Any] = {"agent": "claude-code"}
    for record in records:
        if "cwd" not in metadata and isinstance(record.get("cwd"), str):
            metadata["cwd"] = record["cwd"]
        if "version" not in metadata and isinstance(record.get("version"), str):
            metadata["version"] = record["version"]
        if "model" not in metadata:
            model = (record.get("message") or {}).get("model")
            if isinstance(model, str):
                metadata["model"] = model
        if {"cwd", "version", "model"} <= metadata.keys():
            break
    return metadata


def parse_session(path: Path | str) -> dict[str, Any]:
    """Parse a full session file into a trajectory document."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    metadata = session_metadata(iter_records(text))
    metadata["source"] = str(path)
    metadata["session_id"] = path.stem
    return {"metadata": metadata, "steps": steps_from_session_text(text)}
