"""Antigravity adapter: reads Antigravity session logs.

Antigravity's sessions live under ``~/.gemini/antigravity/brain/<session_id>/log.jsonl``.
The adapter implements ``discover``/``parse_session`` and the tailing hooks for JSONL.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from agentbench.adapters.base import SessionSource, SourceAdapter


def _iter_records(text: str) -> Iterator[dict[str, Any]]:
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


class AntigravityAdapter(SourceAdapter):
    client_name = "antigravity"
    display_name = "Antigravity"
    supports_tail = True
    detect_only = False
    supports_interception = False

    def _roots(self, home: Path) -> list[Path]:
        return [
            home / ".gemini" / "antigravity" / "brain",
        ]

    def detect(self, home: Path) -> bool:
        return any(root.is_dir() for root in self._roots(home))

    def discover(self, home: Path) -> list[SessionSource]:
        sources: list[SessionSource] = []
        for root in self._roots(home):
            if not root.is_dir():
                continue
            try:
                for db_path in root.glob("*/log.jsonl"):
                    modified = db_path.stat().st_mtime
                    sources.append(
                        SessionSource(
                            agent=self.client_name,
                            path=db_path,
                            session_id=db_path.parent.name,
                            modified=modified,
                        )
                    )
            except OSError:
                continue
        return sources

    def parse_session(self, path: Path) -> dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        metadata = self.metadata_from_text(text)
        metadata["source"] = str(path)
        metadata.setdefault("session_id", path.parent.name)
        return {"metadata": metadata, "steps": self.steps_from_text(text)}

    def metadata_from_text(self, text: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {"agent": self.client_name}
        for record in _iter_records(text):
            if "session_id" in record:
                metadata["session_id"] = record["session_id"]
        return metadata

    def steps_from_text(self, text: str) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for record in _iter_records(text):
            if record.get("type") == "tool_call":
                steps.append(record)
        return steps
