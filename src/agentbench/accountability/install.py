"""``agentbench init``: wire enforcement into a project, reversibly.

Two idempotent steps:

1. Register ``agentbench hook`` as a Claude Code PreToolUse hook in the
   project's ``.claude/settings.json`` -- merged, never clobbering existing
   hooks or other settings.
2. Scaffold a starter ``.agentbench/policy.yml`` if none exists.

Both are safe to run repeatedly. Nothing here enforces anything on its own:
the hook is inert until a ``policy.yml`` gives it rules to act on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HOOK_COMMAND = "agentbench hook"
HOOK_MATCHER = "Write|Edit|MultiEdit|Bash"

STARTER_POLICY = """\
# AgentBench enforcement policy. Delete this file to go back to observe-only.
# Docs: https://github.com/casualstack/agentbench-os/blob/main/docs/ENFORCEMENT.md
version: 1

# Default action per alert severity, for any rule without an explicit override
# below. Actions: allow (record only) | ask (prompt you) | deny (block it).
defaults:
  warning: allow
  critical: ask

# Per-rule overrides, keyed by the rule ids AgentBench raises (see
# docs/ACCOUNTABILITY.md). Uncomment and tune to taste.
rules:
  secret_file_write: deny
  potential_secret_exposure: deny
  # destructive_command: ask
  # hook_bypass: deny

# Writes to any path matching these globs are always denied.
protected_paths:
  - ".env*"
  - ".github/workflows/**"

# If the engine or this file itself errors, do this. 'allow' (fail open) never
# wedges your agent on an AgentBench bug; 'deny' (fail closed) is stricter.
on_error: allow
"""


def merge_hook_settings(settings: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return (settings, changed) with our PreToolUse hook ensured present.

    Idempotent: if a PreToolUse group already runs ``agentbench hook`` it's
    left untouched. Other hooks and settings are preserved.
    """
    settings = dict(settings)
    hooks = dict(settings.get("hooks") or {})
    pre = list(hooks.get("PreToolUse") or [])

    for group in pre:
        if not isinstance(group, dict):
            continue
        for h in group.get("hooks") or []:
            if isinstance(h, dict) and h.get("command") == HOOK_COMMAND:
                return settings, False  # already installed

    pre.append({
        "matcher": HOOK_MATCHER,
        "hooks": [{"type": "command", "command": HOOK_COMMAND}],
    })
    hooks["PreToolUse"] = pre
    settings["hooks"] = hooks
    return settings, True


def install_hook(project_root: Path | str) -> bool:
    """Write the merged ``.claude/settings.json``. Returns True if it changed."""
    root = Path(project_root)
    settings_path = root / ".claude" / "settings.json"

    existing: dict[str, Any] = {}
    if settings_path.is_file():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}

    merged, changed = merge_hook_settings(existing)
    if changed:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return changed


def scaffold_policy(project_root: Path | str) -> bool:
    """Write a starter ``.agentbench/policy.yml`` if absent. Returns True if
    it was created."""
    root = Path(project_root)
    policy_path = root / ".agentbench" / "policy.yml"
    if policy_path.is_file():
        return False
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(STARTER_POLICY, encoding="utf-8")
    return True
