"""Codex CLI adapter: parses real rollout JSONL, safe to byte-tail.

Sessions live at ``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl``, one JSON
object per line shaped ``{timestamp, type, payload}``. The records that
matter here:

- ``type: "session_meta"`` — ``payload`` carries ``session_id``, ``cwd``,
  ``cli_version``.
- ``type: "turn_context"`` — ``payload`` carries ``cwd``, ``model``.
- ``type: "response_item"`` with ``payload.type == "function_call"``, name
  ``shell_command`` (or ``shell``) — ``payload.arguments`` is a JSON string
  holding ``command``/``workdir``; normalized to a ``run_command`` step.
- ``type: "response_item"`` with ``payload.type == "custom_tool_call"``,
  name ``apply_patch`` — ``payload.input`` is patch text with
  ``*** Add File:`` / ``*** Update File:`` / ``*** Delete File:`` headers
  and unified-diff-style ``-``/``+`` hunk lines; normalized to one
  ``write_file``/``str_replace`` step per file so the existing
  str_replace-based rules (deleted_assertion, weakened_assertion, ...) fire
  on Codex sessions the same way they do on Claude Code and Cursor ones.

Malformed lines, unknown tools, and unreadable files degrade gracefully —
discovery and parsing never raise.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

from agentbench.watch.adapters.base import SessionSource, SourceAdapter

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_PATCH_HEADER_RE = re.compile(r"^\*\*\* (Add File|Update File|Delete File): (.+)$")


def _session_id_from_filename(path: Path) -> str:
    """Rollout filenames end in the session's UUID — no need to open the file."""
    match = _UUID_RE.search(path.stem)
    return match.group(0) if match else path.stem


def _iter_records(text: str) -> Iterator[dict[str, Any]]:
    """Yield JSON records from rollout text, skipping blank/corrupt lines."""
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


def _step_from_function_call(payload: dict[str, Any]) -> dict[str, Any] | None:
    name = payload.get("name")
    if name not in ("shell_command", "shell"):
        return None
    raw_args = payload.get("arguments")
    if not isinstance(raw_args, str):
        return None
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError:
        return None
    if not isinstance(args, dict):
        return None

    command = args.get("command")
    if isinstance(command, list):
        command = " ".join(str(part) for part in command)
    if not isinstance(command, str) or not command:
        return None

    normalized = dict(args)
    normalized["command"] = command
    return {
        "type": "tool_call",
        "tool": "run_command",
        "args": normalized,
        "agent_tool": name,
    }


def _steps_from_apply_patch(patch_text: str) -> list[dict[str, Any]]:
    """Turn one ``apply_patch`` input into one write step per touched file."""
    blocks: list[tuple[str, str, list[str]]] = []  # (kind, path, body lines)
    current: list[str] | None = None
    for line in patch_text.splitlines():
        header = _PATCH_HEADER_RE.match(line)
        if header:
            kind, path = header.group(1), header.group(2)
            current = []
            blocks.append((kind, path, current))
            continue
        if current is None:
            continue  # before the first header, e.g. "*** Begin Patch"
        if line.startswith("*** ") or line.startswith("@@"):
            continue  # nested markers ("*** Move to:", hunk context) — not content
        current.append(line)

    order: list[str] = []
    by_path: dict[str, dict[str, Any]] = {}
    for kind, path, body in blocks:
        if path not in by_path:
            order.append(path)
            by_path[path] = {"add": None, "update": [], "delete": False}
        if kind == "Add File":
            by_path[path]["add"] = "\n".join(l[1:] for l in body if l.startswith("+"))
        elif kind == "Update File":
            old = "\n".join(l[1:] for l in body if l.startswith("-"))
            new = "\n".join(l[1:] for l in body if l.startswith("+"))
            by_path[path]["update"].append((old, new))
        elif kind == "Delete File":
            by_path[path]["delete"] = True

    steps: list[dict[str, Any]] = []
    for path in order:
        info = by_path[path]
        if info["add"] is not None:
            # Also covers "Delete File: x" + "Add File: x" for the same path —
            # apply_patch's spelling of a full-file rewrite — as one write.
            steps.append(
                {
                    "type": "tool_call",
                    "tool": "write_file",
                    "args": {"file_path": path, "content": info["add"]},
                    "agent_tool": "apply_patch",
                }
            )
        elif info["update"]:
            old = "\n".join(o for o, _ in info["update"])
            new = "\n".join(n for _, n in info["update"])
            steps.append(
                {
                    "type": "tool_call",
                    "tool": "str_replace",
                    "args": {"file_path": path, "old_string": old, "new_string": new},
                    "agent_tool": "apply_patch",
                }
            )
        elif info["delete"]:
            steps.append(
                {
                    "type": "tool_call",
                    "tool": "write_file",
                    "args": {"file_path": path, "content": ""},
                    "agent_tool": "apply_patch",
                }
            )
    return steps


def _metadata_from_records(records: Iterator[dict[str, Any]]) -> dict[str, Any]:
    """Pull session_id/cwd/model/cli_version from rollout records."""
    metadata: dict[str, Any] = {"agent": "codex"}
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        rtype = record.get("type")
        ptype = payload.get("type")

        if rtype == "session_meta" or ptype == "session_meta":
            if "session_id" not in metadata:
                sid = payload.get("session_id") or payload.get("id")
                if isinstance(sid, str):
                    metadata["session_id"] = sid
            if "cwd" not in metadata and isinstance(payload.get("cwd"), str):
                metadata["cwd"] = payload["cwd"]
            if "cli_version" not in metadata and isinstance(payload.get("cli_version"), str):
                metadata["cli_version"] = payload["cli_version"]
        elif rtype == "turn_context" or ptype == "turn_context":
            if "cwd" not in metadata and isinstance(payload.get("cwd"), str):
                metadata["cwd"] = payload["cwd"]
            if "model" not in metadata and isinstance(payload.get("model"), str):
                metadata["model"] = payload["model"]

        if {"cwd", "model"} <= metadata.keys():
            break
    return metadata


def steps_from_records(records: Iterator[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for record in records:
        if record.get("type") != "response_item":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        ptype = payload.get("type")
        if ptype == "function_call":
            step = _step_from_function_call(payload)
            if step is not None:
                steps.append(step)
        elif ptype == "custom_tool_call" and payload.get("name") == "apply_patch":
            patch_text = payload.get("input")
            if isinstance(patch_text, str):
                steps.extend(_steps_from_apply_patch(patch_text))
    return steps


class CodexAdapter(SourceAdapter):
    """Sessions live under ``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl``."""

    client_name = "codex"
    display_name = "Codex CLI"
    supports_tail = True  # append-only JSONL, safe to byte-tail
    detect_only = False

    def _sessions_root(self, home: Path) -> Path:
        return home / ".codex" / "sessions"

    def detect(self, home: Path) -> bool:
        return self._sessions_root(home).is_dir()

    def discover(self, home: Path) -> list[SessionSource]:
        sources: list[SessionSource] = []
        root = self._sessions_root(home)
        try:
            paths = list(root.rglob("rollout-*.jsonl"))
        except OSError:
            return sources
        for path in paths:
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            sources.append(
                SessionSource(
                    agent=self.client_name,
                    path=path,
                    session_id=_session_id_from_filename(path),
                    modified=modified,
                )
            )
        return sources

    def parse_session(self, path: Path) -> dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        metadata = self.metadata_from_text(text)
        metadata["source"] = str(path)
        metadata.setdefault("session_id", _session_id_from_filename(path))
        return {"metadata": metadata, "steps": self.steps_from_text(text)}

    def metadata_from_text(self, text: str) -> dict[str, Any]:
        return _metadata_from_records(_iter_records(text))

    def steps_from_text(self, text: str) -> list[dict[str, Any]]:
        return steps_from_records(_iter_records(text))
