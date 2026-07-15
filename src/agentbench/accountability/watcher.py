"""Tail agent session logs and emit alerts as new steps appear.

Two strategies, chosen per adapter via ``supports_tail``:

- Tailable (append-only JSONL, e.g. Claude Code): byte-tail the file —
  track a read offset, parse only newly-appended complete lines. Polling,
  not filesystem events: a poll every couple of seconds is plenty, needs no
  dependencies, and behaves identically on Windows, macOS, and Linux.
- Non-tailable (e.g. Cursor's SQLite store): there's no append-only log to
  byte-tail, so we re-parse the whole session on each poll (only when its
  mtime has moved) and diff the resulting step count against what we saw
  last time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentbench.accountability.policy import ObservePolicyEngine, PolicyContext, PolicyEngine
from agentbench.accountability.rules import Alert, check_step
from agentbench.accountability.sources import DiscoveryReport, discover_sessions
from agentbench.adapters import ADAPTERS
from agentbench.adapters.base import SourceAdapter

_ADAPTERS_BY_NAME: dict[str, SourceAdapter] = {a.client_name: a for a in ADAPTERS}


def _adapter_for(agent: str) -> SourceAdapter | None:
    return _ADAPTERS_BY_NAME.get(agent)


@dataclass
class _SessionState:
    """Per-session watching state."""

    agent: str
    path: Path
    session_id: str
    offset: int = 0  # tailable sources: read offset in bytes
    remainder: str = ""  # tailable sources: partial last line from previous read
    reparse_mtime: float | None = None  # non-tailable sources: mtime last parsed
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
        policy_engine: PolicyEngine | None = None,
    ) -> None:
        self._home = home
        self._project = str(project) if project is not None else None
        self._skip_existing = skip_existing
        self._sessions: dict[Path, _SessionState] = {}
        self._primed = False
        self._last_report: DiscoveryReport | None = None
        # Phase 2 seam: ObservePolicyEngine always ALLOWs, and its verdict
        # is discarded below -- accountability only, no enforcement yet.
        self._policy_engine = policy_engine or ObservePolicyEngine()

    # -- public -----------------------------------------------------------

    def poll(self) -> list[WatchEvent]:
        """Scan for new/grown session files; evaluate and return new activity."""
        report = discover_sessions(self._home)
        self._last_report = report
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
        result = []
        for s in self._sessions.values():
            adapter = _adapter_for(s.agent)
            result.append(
                {
                    "agent": s.agent,
                    "client": adapter.display_name if adapter else s.agent,
                    "session_id": s.session_id,
                    "path": str(s.path),
                    "cwd": s.cwd,
                    "model": s.model,
                    "steps": s.step_count,
                    "alerts": [a.to_dict() for a in s.alerts],
                }
            )
        return result

    def detected_agents(self) -> list[str]:
        """Detected agents from the last poll(), or a fresh scan if never polled."""
        if self._last_report is None:
            self._last_report = discover_sessions(self._home)
        return self._last_report.detected_agents

    # -- internals ----------------------------------------------------------

    def _register_new(self, report: DiscoveryReport) -> None:
        for source in report.sessions:
            if source.path in self._sessions:
                continue
            adapter = _adapter_for(source.agent)
            if adapter is None:
                continue
            state = _SessionState(
                agent=source.agent, path=source.path, session_id=source.session_id
            )
            if self._skip_existing and not self._primed:
                self._prime_skip_existing(state, adapter)
            self._sessions[source.path] = state

    def _prime_skip_existing(self, state: _SessionState, adapter: SourceAdapter) -> None:
        """Jump a freshly-seen session past its current content."""
        if adapter.supports_tail:
            try:
                state.offset = state.path.stat().st_size
            except OSError:
                pass
            self._fill_metadata(state, adapter)
        else:
            # No offset to jump to — re-parse once and treat every step
            # already there as history rather than new activity.
            doc = self._safe_parse(adapter, state.path)
            if doc is None:
                return
            state.step_count = len(doc.get("steps") or [])
            self._apply_metadata(state, doc.get("metadata") or {})
            try:
                state.reparse_mtime = state.path.stat().st_mtime
            except OSError:
                pass

    def _fill_metadata(self, state: _SessionState, adapter: SourceAdapter) -> None:
        try:
            text = state.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        try:
            metadata = adapter.metadata_from_text(text)
        except Exception:
            return
        self._apply_metadata(state, metadata)

    def _apply_metadata(self, state: _SessionState, metadata: dict[str, Any]) -> None:
        state.cwd = state.cwd or metadata.get("cwd")
        state.model = state.model or metadata.get("model")

    def _safe_parse(self, adapter: SourceAdapter, path: Path) -> dict[str, Any] | None:
        try:
            return adapter.parse_session(path)
        except Exception:
            return None

    def _drain(self, state: _SessionState) -> WatchEvent | None:
        adapter = _adapter_for(state.agent)
        if adapter is None:
            return None
        if adapter.supports_tail:
            return self._drain_tail(state, adapter)
        return self._drain_reparse(state, adapter)

    def _drain_tail(self, state: _SessionState, adapter: SourceAdapter) -> WatchEvent | None:
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

        if state.cwd is None or state.model is None:
            try:
                self._apply_metadata(state, adapter.metadata_from_text(text))
            except Exception:
                pass

        try:
            steps = adapter.steps_from_text(text)
        except Exception:
            steps = []
        if not steps:
            return None

        return self._evaluate_new_steps(state, steps)

    def _drain_reparse(self, state: _SessionState, adapter: SourceAdapter) -> WatchEvent | None:
        """Re-parse the whole session and diff against the last step count.

        Used for sources with no append-only log to byte-tail (e.g. Cursor's
        SQLite store). This loses fine-grained ordering if a source rewrites
        earlier steps in place rather than only appending — acceptable for
        now since these sources are best-effort to begin with.
        """
        try:
            mtime = state.path.stat().st_mtime
        except OSError:
            return None
        if state.reparse_mtime is not None and mtime <= state.reparse_mtime:
            return None
        state.reparse_mtime = mtime

        doc = self._safe_parse(adapter, state.path)
        if doc is None:
            return None
        self._apply_metadata(state, doc.get("metadata") or {})

        all_steps = doc.get("steps") or []
        new_steps = all_steps[state.step_count :]
        if not new_steps:
            return None

        return self._evaluate_new_steps(state, new_steps)

    def _evaluate_new_steps(
        self, state: _SessionState, steps: list[dict[str, Any]]
    ) -> WatchEvent | None:
        if self._project is not None and not _cwd_matches(state.cwd, self._project):
            state.step_count += len(steps)
            return None

        # Same loop check_steps() runs internally, unrolled here so each
        # step's alerts can also feed the Phase 2 policy seam below.
        alerts: list[Alert] = []
        for i, step in enumerate(steps):
            step_index = state.step_count + i
            step_alerts = check_step(step, step_index, cwd=state.cwd)
            alerts.extend(step_alerts)

            # Phase 2 seam: verdict is computed and discarded, never acted
            # on. ObservePolicyEngine always ALLOWs, so this changes zero
            # observable behavior in Phase 1.
            self._policy_engine.evaluate(
                PolicyContext(
                    agent=state.agent,
                    session_id=state.session_id,
                    cwd=state.cwd,
                    step=step,
                    step_index=step_index,
                    alerts=step_alerts,
                )
            )

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
    from agentbench.accountability.rules import is_within

    return is_within(cwd, project) or is_within(project, cwd)
