"""The interface every agent-source adapter implements.

An adapter knows three things about one coding agent: whether it's present
on this machine (``detect``), where its session data lives (``discover``),
and how to turn one session into AgentBench's normalized step vocabulary
(``parse_session``). ``supports_tail`` tells the watcher whether sessions
are append-only JSONL logs that are safe to byte-tail, or need a full
re-parse on each poll (see ``adapters.cursor``).

Add a new client by subclassing ``SourceAdapter`` and registering an
instance in ``adapters.ADAPTERS``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SessionSource:
    """One discoverable agent session, before parsing."""

    agent: str  # adapter's client_name, e.g. "claude-code", "cursor"
    path: Path
    session_id: str
    modified: float
    project_slug: str | None = None


class SourceAdapter(ABC):
    """Base class for one coding agent's session source."""

    client_name: str  # canonical id, e.g. "claude-code"
    display_name: str  # human label, e.g. "Claude Code"
    supports_tail: bool = False  # True for append-only JSONL logs
    detect_only: bool = False  # True for stubs that detect but can't parse yet

    @abstractmethod
    def detect(self, home: Path) -> bool:
        """Is this agent's session data present on this machine?"""

    @abstractmethod
    def discover(self, home: Path) -> list[SessionSource]:
        """Enumerate this agent's sessions. Order doesn't matter (the
        registry sorts everything by modified time)."""

    @abstractmethod
    def parse_session(self, path: Path) -> dict[str, Any]:
        """Parse one full session into ``{"metadata": {...}, "steps": [...]}``."""

    # -- tailing hooks --------------------------------------------------
    # Only called when supports_tail is True. Given a chunk of raw session
    # text (as read off disk, not necessarily the whole file), extract
    # metadata/steps from it. Adapters that don't support tailing never
    # need to implement these.

    def metadata_from_text(self, text: str) -> dict[str, Any]:
        raise NotImplementedError

    def steps_from_text(self, text: str) -> list[dict[str, Any]]:
        raise NotImplementedError
