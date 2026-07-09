"""Tail agent session logs and emit alerts as new steps appear.

Polling, not filesystem events: session files grow by appended JSONL lines,
a poll every couple of seconds is plenty, and polling needs no dependencies
and behaves identically on Windows, macOS, and Linux.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentbench.watch.claude_code import (
    iter_records,
    session_metadata,
    steps_from_records,
)
from agentbench.watch.rules import Alert, check_steps
from agentbench.watch.sources import DiscoveryReport, discover_sessions


@dataclass
class _SessionState:
    """Per-file tailing state."""

    agent: str
    path: Path
    session_id: str
    offset: int = 0
    remainder: str = ""  # partial last line from the previous read
    step_count: int = 0
    cwd: str | None = None
    model: str | None = None
    alerts: list[Alert] = field(default_factory=list)


@dataclass
class WatchEvent:
    """New activity observed in one session during a poll."""

    agent: str
    session_id: str
    path: Path
    cwd: str | None
    model: str | None
    new_steps: int
    alerts: list[Alert]


class SessionWatcher:
    """Discover sessions and incrementally evaluate their new steps.

    ``poll()`` returns one WatchEvent per session that grew since last time.
    ``project`` limits watching to sessions whose cwd is under that folder.
    """

    def __init__(
        self,
        *,
        home: Path | None = None,
        project: Path | str | None = None,
        skip_existing: bool = False,
    ) -> None:
        self._home = home
        self._project = str(project) if project is not None else None
        self._skip_existing = skip_existing
        self._sessions: dict[Path, _SessionState] = {}
        self._primed = False

    # -- public -----------------------------------------------------------

    def poll(self) -> list[WatchEvent]:
        """Scan for new/grown session files; evaluate and return new activity."""
        report = discover_sessions(self._home)
        self._register_new(report)

        events: list[WatchEvent] = []
        for state in self._sessions.values():
            event = self._drain(state)
            if event is not None:
                events.append(event)
        self._primed = True
        return events

    def sessions(self) -> list[dict[str, Any]]:
        """Snapshot of everything watched so far (for UI/API use)."""
        return [
            {
                "agent": s.agent,
                "session_id": s.session_id,
                "path": str(s.path),
                "cwd": s.cwd,
                "model": s.model,
                "steps": s.step_count,
                "alerts": [a.to_dict() for a in s.alerts],
            }
            for s in self._sessions.values()
        ]

    def detected_agents(self) -> list[str]:
        return discover_sessions(self._home).detected_agents

    # -- internals ----------------------------------------------------------

    def _register_new(self, report: DiscoveryReport) -> None:
        for source in report.sessions:
            if source.agent != "claude-code" or source.path in self._sessions:
                continue
            state = _SessionState(
                agent=source.agent, path=source.path, session_id=source.session_id
            )
            if self._skip_existing and not self._primed:
                # Only watch activity from now on; jump past current content.
                try:
                    state.offset = source.path.stat().st_size
                except OSError:
                    pass
                self._fill_metadata(state)
            self._sessions[source.path] = state

    def _fill_metadata(self, state: _SessionState) -> None:
        try:
            text = state.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        self._apply_metadata(state, session_metadata(iter_records(text)))

    def _apply_metadata(self, state: _SessionState, metadata: dict[str, Any]) -> None:
        state.cwd = state.cwd or metadata.get("cwd")
        state.model = state.model or metadata.get("model")

    def _drain(self, state: _SessionState) -> WatchEvent | None:
        """Read appended bytes, parse complete lines, evaluate new steps."""
        try:
            size = state.path.stat().st_size
        except OSError:
            return None
        if size < state.offset:  # truncated/rotated: start over
            state.offset = 0
            state.remainder = ""
        if size == state.offset:
            return None

        try:
            with state.path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(state.offset)
                chunk = handle.read()
                state.offset = handle.tell()
        except OSError:
            return None

        text = state.remainder + chunk
        # Keep a trailing partial line for the next poll.
        if text.endswith("\n"):
            state.remainder = ""
        else:
            text, _, state.remainder = text.rpartition("\n")
            if not text and state.remainder:
                return None

        records = list(iter_records(text))
        if state.cwd is None or state.model is None:
            self._apply_metadata(state, session_metadata(iter(records)))

        steps = steps_from_records(iter(records))
        if not steps:
            return None

        if self._project is not None and not _cwd_matches(state.cwd, self._project):
            state.step_count += len(steps)
            return None

        alerts = check_steps(steps, cwd=state.cwd, start_index=state.step_count)
        state.step_count += len(steps)
        state.alerts.extend(alerts)

        return WatchEvent(
            agent=state.agent,
            session_id=state.session_id,
            path=state.path,
            cwd=state.cwd,
            model=state.model,
            new_steps=len(steps),
            alerts=alerts,
        )


def _cwd_matches(cwd: str | None, project: str) -> bool:
    if cwd is None:
        return False
    from agentbench.watch.rules import is_within

    return is_within(cwd, project) or is_within(project, cwd)
