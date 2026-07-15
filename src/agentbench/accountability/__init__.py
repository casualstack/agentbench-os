"""Zero-config session watching: auto-detect agent sessions, raise plain-English alerts."""

from agentbench.accountability.audit import AuditStore
from agentbench.accountability.rules import Alert, check_steps
from agentbench.accountability.session_parser import parse_session, steps_from_session_text
from agentbench.accountability.sources import SessionSource, discover_sessions
from agentbench.accountability.watcher import SessionWatcher, WatchEvent
from agentbench.adapters import ADAPTERS, SourceAdapter

__all__ = [
    "ADAPTERS",
    "Alert",
    "AuditStore",
    "SessionSource",
    "SessionWatcher",
    "SourceAdapter",
    "WatchEvent",
    "check_steps",
    "discover_sessions",
    "parse_session",
    "steps_from_session_text",
]
