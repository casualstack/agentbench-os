"""Load and validate ``.agentbench/policy.yml`` for the Phase 2 engine.

The config is read and validated **once** (here, at engine construction
time) so that ``ConfigPolicyEngine.evaluate()`` can stay synchronous and
side-effect-free -- see ``engine.py`` and the seam requirement it inherits.

Schema (version 1)::

    version: 1
    defaults:              # per-severity action for any step that raises an alert
      warning: allow       # allow | deny | ask
      critical: ask
    rules:                 # per-rule overrides, keyed by rule id from rules.py
      secret_file_write: deny
      destructive_command: ask
    protected_paths:       # writes to a matching path are always denied
      - ".github/workflows/**"
      - ".env*"
    on_error: allow        # what to do if the engine/config itself fails

Precedence: a repo-local ``./.agentbench/policy.yml`` wins over the global
``~/.agentbench/policy.yml``; if neither exists, ``load_policy`` returns
``None`` and callers fall back to observe-only (``ObservePolicyEngine``).
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agentbench.accountability.rules import CRITICAL, WARNING

# The actions a policy can take on a step. These map onto the Decision enum
# (see decision.py) and, in the hook, onto Claude Code's permission model:
#   allow -> stay out of the way (normal permission flow)
#   ask   -> force a human approval prompt
#   deny  -> block the step before it runs
Action = Literal["allow", "ask", "deny"]

# Restrictiveness ordering, used to pick the strongest action when several
# apply to one step. Higher wins.
_ACTION_RANK: dict[str, int] = {"allow": 0, "ask": 1, "deny": 2}


class PolicyConfigError(ValueError):
    """Raised when policy.yml exists but can't be read or validated."""


class PolicyConfig(BaseModel):
    """A validated ``.agentbench/policy.yml``."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    defaults: dict[str, Action] = Field(
        default_factory=lambda: {WARNING: "allow", CRITICAL: "ask"}
    )
    rules: dict[str, Action] = Field(default_factory=dict)
    protected_paths: list[str] = Field(default_factory=list)
    on_error: Literal["allow", "deny"] = "allow"

    def action_for_severity(self, severity: str) -> Action:
        return self.defaults.get(severity, "allow")

    def action_for_rule(self, rule: str, severity: str) -> Action:
        """Most specific action for one alert: rule override beats the
        per-severity default."""
        if rule in self.rules:
            return self.rules[rule]
        return self.action_for_severity(severity)

    def matches_protected_path(self, path: str | None) -> bool:
        """True if ``path`` matches any protected-path glob.

        Matched permissively against the path as given, its POSIX form, its
        cwd-agnostic basename, and any tail segment -- so a pattern like
        ``.env*`` catches ``/home/u/proj/.env.local`` and
        ``.github/workflows/**`` catches an absolute path ending in that.
        """
        if not path:
            return False
        norm = path.replace("\\", "/")
        candidates = {norm, norm.lstrip("/"), Path(norm).name}
        # Also try every path suffix so patterns anchored at the repo root
        # (".github/workflows/**") match absolute paths that end with them.
        parts = norm.split("/")
        for i in range(len(parts)):
            candidates.add("/".join(parts[i:]))
        for pattern in self.protected_paths:
            pat = pattern.replace("\\", "/")
            for cand in candidates:
                if fnmatch.fnmatch(cand, pat):
                    return True
        return False


def most_restrictive(actions: list[Action]) -> Action:
    """Return the strongest of several actions (deny > ask > allow)."""
    if not actions:
        return "allow"
    return max(actions, key=lambda a: _ACTION_RANK.get(a, 0))


def _load_file(path: Path) -> PolicyConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PolicyConfigError(f"Could not read policy file {path}: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise PolicyConfigError(f"Policy file {path} must be a YAML mapping.")
    try:
        return PolicyConfig.model_validate(raw)
    except ValidationError as exc:
        raise PolicyConfigError(f"Invalid policy in {path}:\n{exc}") from exc


def policy_paths(project_root: Path | str | None, home: Path | None) -> list[Path]:
    """Candidate policy locations, in precedence order (first found wins)."""
    home = home or Path.home()
    paths: list[Path] = []
    if project_root is not None:
        paths.append(Path(project_root) / ".agentbench" / "policy.yml")
    paths.append(home / ".agentbench" / "policy.yml")
    return paths


def load_policy(
    project_root: Path | str | None = None,
    home: Path | None = None,
) -> PolicyConfig | None:
    """Load the first policy.yml that exists, or None for observe-only.

    Raises ``PolicyConfigError`` if a file exists but is malformed -- callers
    decide whether that's fatal or should fail open (the hook fails open and
    records the failure).
    """
    for path in policy_paths(project_root, home):
        if path.is_file():
            return _load_file(path)
    return None
