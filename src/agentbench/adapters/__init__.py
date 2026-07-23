"""Registry of pluggable agent-source adapters.

``discover_sessions()`` (in ``watch.sources``) iterates this list. Add a new
client by subclassing ``SourceAdapter`` and appending an instance here.
"""

from __future__ import annotations

from agentbench.adapters.antigravity import AntigravityAdapter
from agentbench.adapters.base import SessionSource, SourceAdapter
from agentbench.adapters.claude_code import ClaudeCodeAdapter
from agentbench.adapters.codex import CodexAdapter
from agentbench.adapters.cursor import CursorAdapter

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
