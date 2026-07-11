"""Claude Code adapter: one JSONL file per session, safe to byte-tail.

The actual parsing lives in ``agentbench.watch.claude_code`` (kept in place
since ``watcher.py`` and existing tests import those functions directly);
this module just wraps that logic behind the ``SourceAdapter`` interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentbench.watch.adapters.base import SessionSource, SourceAdapter
from agentbench.watch.claude_code import (
    iter_records,
    parse_session,
    session_metadata,
    steps_from_session_text,
)


class ClaudeCodeAdapter(SourceAdapter):
    """Sessions live under ``~/.claude/projects/<project-slug>/<session-id>.jsonl``."""

    client_name = "claude-code"
    display_name = "Claude Code"
    supports_tail = True  # append-only JSONL, safe to byte-tail

    def _root(self, home: Path) -> Path:
        return home / ".claude" / "projects"

    def detect(self, home: Path) -> bool:
        return self._root(home).is_dir()

    def discover(self, home: Path) -> list[SessionSource]:
        sources: list[SessionSource] = []
        for path in self._root(home).glob("*/*.jsonl"):
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            sources.append(
                SessionSource(
                    agent=self.client_name,
                    path=path,
                    session_id=path.stem,
                    modified=modified,
                    project_slug=path.parent.name,
                )
            )
        return sources

    def parse_session(self, path: Path) -> dict[str, Any]:
        return parse_session(path)

    def metadata_from_text(self, text: str) -> dict[str, Any]:
        return session_metadata(iter_records(text))

    def steps_from_text(self, text: str) -> list[dict[str, Any]]:
        return steps_from_session_text(text)
