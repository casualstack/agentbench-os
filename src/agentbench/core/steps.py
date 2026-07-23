"""Shared tool-call vocabulary: which tools write files or run commands,
and how to pull a path/command out of their args.

Both pillars need this: ``accountability/rules.py`` uses it to decide which
alerts apply to a step, and ``core/trajectory.py`` uses it to walk a
recorded trajectory for the eval pillar. Previously each side defined its
own copy of the tool-name sets and key-precedence lookups; this is the
single source of truth for both.
"""

from __future__ import annotations

from typing import Any

WRITE_TOOLS = {"write_file", "edit_file", "str_replace", "Write", "StrReplace"}
RUN_TOOLS = {"run_command", "shell", "bash", "Bash", "execute"}


def step_path(args: dict[str, Any]) -> str | None:
    for key in ("path", "file_path", "target_file"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def step_command(args: dict[str, Any]) -> str | None:
    for key in ("command", "cmd"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return None
