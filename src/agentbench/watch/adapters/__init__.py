"""Registry of pluggable agent-source adapters.

``discover_sessions()`` (in ``watch.sources``) iterates this list. Add a new
client by subclassing ``SourceAdapter`` and appending an instance here.
"""

from __future__ import annotations

from agentbench.watch.adapters.antigravity import AntigravityAdapter
from agentbench.watch.adapters.base import SessionSource, SourceAdapter
from agentbench.watch.adapters.claude_code import ClaudeCodeAdapter
from agentbench.watch.adapters.codex import CodexAdapter
from agentbench.watch.adapters.cursor import CursorAdapter

ADAPTERS: list[SourceAdapter] = [
    ClaudeCodeAdapter(),
    CursorAdapter(),
    CodexAdapter(),
    AntigravityAdapter(),
]

__all__ = [
    "ADAPTERS",
    "AntigravityAdapter",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "CursorAdapter",
    "SessionSource",
    "SourceAdapter",
]
