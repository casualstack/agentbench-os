"""Discover agent session logs on this machine.

Claude Code is the first-class source: it writes one JSONL file per session
under ``~/.claude/projects/<project-slug>/<session-id>.jsonl``. Cursor is
detected but not yet parsed (its sessions live in a SQLite store, not JSONL);
we surface its presence honestly so the UI can say "support coming".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SessionSource:
    """One discoverable agent session log."""

    agent: str  # "claude-code" (parseable) or "cursor" (detected only)
    path: Path
    session_id: str
    modified: float
    project_slug: str | None = None


@dataclass
class DiscoveryReport:
    """Everything we found on this machine, plus detected-but-unsupported agents."""

    sessions: list[SessionSource] = field(default_factory=list)
    detected_agents: list[str] = field(default_factory=list)


def claude_code_root(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".claude" / "projects"


def _cursor_roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    candidates = [
        home / ".cursor",  # linux/mac CLI state
        home / "Library" / "Application Support" / "Cursor",  # macOS
        home / ".config" / "Cursor",  # linux
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Cursor")
    return candidates


def discover_sessions(home: Path | None = None) -> DiscoveryReport:
    """Scan known agent locations; newest sessions first."""
    report = DiscoveryReport()

    root = claude_code_root(home)
    if root.is_dir():
        report.detected_agents.append("claude-code")
        for path in root.glob("*/*.jsonl"):
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            report.sessions.append(
                SessionSource(
                    agent="claude-code",
                    path=path,
                    session_id=path.stem,
                    modified=modified,
                    project_slug=path.parent.name,
                )
            )

    if any(p.is_dir() for p in _cursor_roots(home)):
        report.detected_agents.append("cursor")

    report.sessions.sort(key=lambda s: s.modified, reverse=True)
    return report
