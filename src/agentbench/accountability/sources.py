"""Discover agent session logs on this machine.

Discovery is delegated to a registry of ``SourceAdapter`` implementations
(see ``agentbench.adapters``) — Claude Code, Cursor, Codex, Antigravity. Each
adapter says whether its agent is present and, if so, hands back the
sessions it found. A misbehaving adapter never takes discovery down with
it: detection/enumeration failures are caught and that adapter is skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agentbench.adapters import ADAPTERS
from agentbench.adapters.base import SessionSource, SourceAdapter

__all__ = ["DiscoveryReport", "SessionSource", "discover_sessions"]


@dataclass
class DiscoveryReport:
    """Everything we found on this machine, plus detected-but-unsupported agents."""

    sessions: list[SessionSource] = field(default_factory=list)
    detected_agents: list[str] = field(default_factory=list)


def discover_sessions(home: Path | None = None) -> DiscoveryReport:
    """Scan every registered adapter; newest sessions first."""
    home = home or Path.home()
    report = DiscoveryReport()

    for adapter in ADAPTERS:
        if not _safe_detect(adapter, home):
            continue
        report.detected_agents.append(adapter.client_name)
        report.sessions.extend(_safe_discover(adapter, home))

    report.sessions.sort(key=lambda s: s.modified, reverse=True)
    return report


def _safe_detect(adapter: SourceAdapter, home: Path) -> bool:
    try:
        return adapter.detect(home)
    except Exception:
        return False


def _safe_discover(adapter: SourceAdapter, home: Path) -> list[SessionSource]:
    try:
        return adapter.discover(home)
    except Exception:
        return []
