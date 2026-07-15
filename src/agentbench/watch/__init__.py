"""Zero-config session watching: auto-detect agent sessions, raise plain-English alerts."""

from agentbench.adapters import ADAPTERS, SourceAdapter
from agentbench.watch.claude_code import parse_session, steps_from_session_text
from agentbench.watch.rules import Alert, check_steps
from agentbench.watch.sources import SessionSource, discover_sessions
from agentbench.watch.watcher import SessionWatcher, WatchEvent

__all__ = [
    "ADAPTERS",
    "Alert",
    "SessionSource",
    "SessionWatcher",
    "SourceAdapter",
    "WatchEvent",
    "check_steps",
    "discover_sessions",
    "parse_session",
    "steps_from_session_text",
]
