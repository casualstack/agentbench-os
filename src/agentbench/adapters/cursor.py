"""Cursor adapter: best-effort reader of Cursor's local SQLite chat store.

Cursor keeps no per-session JSONL log. Instead, every workspace gets a
``state.vscdb`` file under ``.../User/workspaceStorage/<hash>/state.vscdb``
— a plain ``ItemTable(key TEXT, value BLOB)`` k/v store, not a documented
format. Composer/chat conversations live in there under keys like
``composerData:<id>``, whose shape has already changed across Cursor
releases and will keep changing.

This adapter is deliberately defensive: it never raises out of discovery or
parsing. Any DB that's absent, locked, malformed, or shaped differently
than we expect degrades to "detected, metadata only" rather than guessing
at content — see the module docstring on ``SourceAdapter`` for the contract.
``supports_tail`` is False: there's no append-only log to byte-tail, so the
watcher re-parses the whole DB on each poll and diffs by step count.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from agentbench.adapters.base import SessionSource, SourceAdapter

# Cursor's internal tool names, mapped to the canonical AgentBench
# vocabulary. Best-effort and incomplete on purpose: these names are
# undocumented, so unknown tools are skipped rather than guessed at.
_TOOL_MAP = {
    "write": "write_file",
    "create_file": "write_file",
    "edit_file": "str_replace",
    "search_replace": "str_replace",
    "run_terminal_command": "run_command",
    "run_terminal_cmd": "run_command",
    "web_search": "web_search",
}


class CursorAdapter(SourceAdapter):
    client_name = "cursor"
    display_name = "Cursor"
    supports_tail = False  # re-parsed and diffed by step count on each poll
    supports_interception = False  # observation-only in Phase 1

    def _workspace_storage_roots(self, home: Path) -> list[Path]:
        # Deliberately derived from `home` rather than read from the real
        # %APPDATA% env var, so a caller passing a fake `home` (tests) gets
        # full isolation instead of picking up whatever's actually
        # installed on the machine running the tests.
        return [
            home / ".cursor" / "User" / "workspaceStorage",  # linux/mac CLI state
            home
            / "Library"
            / "Application Support"
            / "Cursor"
            / "User"
            / "workspaceStorage",  # macOS
            home / ".config" / "Cursor" / "User" / "workspaceStorage",  # linux
            home / "AppData" / "Roaming" / "Cursor" / "User" / "workspaceStorage",  # Windows
        ]

    def _workspace_dbs(self, home: Path) -> list[Path]:
        dbs: list[Path] = []
        for root in self._workspace_storage_roots(home):
            if not root.is_dir():
                continue
            try:
                dbs.extend(root.glob("*/state.vscdb"))
            except OSError:
                continue
        return dbs

    def detect(self, home: Path) -> bool:
        return bool(self._workspace_dbs(home))

    def discover(self, home: Path) -> list[SessionSource]:
        sources: list[SessionSource] = []
        for db_path in self._workspace_dbs(home):
            try:
                modified = db_path.stat().st_mtime
            except OSError:
                continue
            sources.append(
                SessionSource(
                    agent=self.client_name,
                    path=db_path,
                    session_id=db_path.parent.name,  # workspace hash
                    modified=modified,
                )
            )
        return sources

    def parse_session(self, path: Path) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "agent": self.client_name,
            "source": str(path),
            "session_id": path.parent.name,
        }
        try:
            steps = self._read_steps(path)
        except Exception:
            # Locked DB, unknown schema, corrupt blob — anything goes wrong
            # here and we degrade to metadata-only instead of guessing.
            steps = []
        return {"metadata": metadata, "steps": steps}

    def _read_steps(self, path: Path) -> list[dict[str, Any]]:
        # Read-only, immutable-safe connection: never write to a live IDE's DB.
        uri = f"file:{path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=1.0)
        try:
            rows = conn.execute(
                "SELECT value FROM ItemTable WHERE key LIKE 'composerData:%'"
            ).fetchall()
        finally:
            conn.close()

        steps: list[dict[str, Any]] = []
        for (value,) in rows:
            steps.extend(self._steps_from_composer_blob(value))
        return steps

    def _steps_from_composer_blob(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode("utf-8")
            except UnicodeDecodeError:
                return []
        if not isinstance(value, str):
            return []
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, dict):
            return []

        conversation = data.get("conversation")
        if not isinstance(conversation, list):
            return []

        steps: list[dict[str, Any]] = []
        for entry in conversation:
            if not isinstance(entry, dict):
                continue
            step = self._step_from_entry(entry)
            if step is not None:
                steps.append(step)
        return steps

    def _step_from_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        tool_data = entry.get("toolFormerData")
        if not isinstance(tool_data, dict):
            return None
        name = tool_data.get("name")
        if not isinstance(name, str):
            return None
        canonical = _TOOL_MAP.get(name)
        if canonical is None:
            return None  # unrecognized tool: skip rather than guess

        args = tool_data.get("params")
        if not isinstance(args, dict):
            raw = tool_data.get("rawArgs")
            args = {}
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    args = parsed

        return {
            "type": "tool_call",
            "tool": canonical,
            "args": args,
            "agent_tool": name,
        }
