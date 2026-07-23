"""Phase 2 policy seam types (design-only skeleton, no enforcement engine).

These types exist now so Phase 2 can slot a real PolicyEngine in later
without touching SessionWatcher's call site again. Phase 1 ships exactly
one engine -- ObservePolicyEngine (see engine.py), which always ALLOWs --
wired into the poll loop as a no-op pass-through: its verdict is computed
and then discarded, never acted on. See docs/ACCOUNTABILITY.md for the
Phase 2 roadmap and the per-client interception reality-check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentbench.accountability.rules import Alert


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class PolicyContext:
    """Everything a policy engine needs to decide on one step.

    ``step`` is the same normalized {"tool":..., "args":...} shape
    ``rules.check_step()`` consumes -- transport-agnostic, so a future
    hook-based interception adapter can build one of these without
    knowing anything about SessionWatcher's internals.
    """

    agent: str
    session_id: str
    cwd: str | None
    step: dict[str, Any]
    step_index: int
    alerts: list["Alert"] = field(default_factory=list)


@dataclass
class PolicyVerdict:
    """What a policy engine decided, and why."""

    decision: Decision
    reason: str
    rule: str | None = None
