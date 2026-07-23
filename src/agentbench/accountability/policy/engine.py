"""Phase 2 policy engine seam (design-only skeleton -- no real engine yet).

``ObservePolicyEngine`` is Phase 1's only implementation: it always
ALLOWs, so wiring it into ``SessionWatcher`` changes zero observable
behavior. A real engine (Phase 2, not built here) would read
``.agentbench/policy.yml`` and return real ALLOW/DENY/REQUIRE_APPROVAL
verdicts -- see docs/ACCOUNTABILITY.md for the design target and the
per-client interception reality-check.

Seam requirement from the reviewer: ``evaluate()`` must stay synchronous
and side-effect-free (regex/in-memory only, no file/network I/O) so a
future hook-based interception adapter can call it inside a tight
latency budget without a redesign.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from agentbench.accountability.policy.config import (
    Action,
    PolicyConfig,
    most_restrictive,
)
from agentbench.accountability.policy.decision import Decision, PolicyContext, PolicyVerdict
from agentbench.core.steps import WRITE_TOOLS, step_path

_ACTION_TO_DECISION: dict[Action, Decision] = {
    "allow": Decision.ALLOW,
    "ask": Decision.REQUIRE_APPROVAL,
    "deny": Decision.DENY,
}


class PolicyEngine(ABC):
    """Decides what should happen to one step. Phase 1 never acts on this."""

    # What a caller should do if evaluate() itself errors. Observe-only
    # engines never enforce, so their safe fallback is always "allow".
    on_error: str = "allow"

    @abstractmethod
    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict:
        ...


class ObservePolicyEngine(PolicyEngine):
    """Phase 1 default. Always ALLOW -- accountability only, no enforcement."""

    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict:
        return PolicyVerdict(Decision.ALLOW, reason="phase1: observe-only")


class ConfigPolicyEngine(PolicyEngine):
    """Real Phase 2 engine, driven by a validated ``.agentbench/policy.yml``.

    The config is loaded and validated by the caller (see ``config.load_policy``)
    and handed in here, so ``evaluate()`` does only in-memory, side-effect-free
    work -- honoring the seam requirement that it be safe to call inside a hook's
    tight latency budget.

    Decision order for one step:

    1. A write to a ``protected_paths`` glob -> DENY (independent of any rule).
    2. Otherwise the most restrictive action across the step's alerts, where
       each alert's action is its per-rule override or the per-severity default.
    3. No protected-path hit and no alerts -> ALLOW.
    """

    def __init__(self, config: PolicyConfig) -> None:
        self._config = config

    @property
    def on_error(self) -> str:  # honored by the hook's fail-safe backstop
        return self._config.on_error

    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict:
        step = ctx.step or {}
        tool = step.get("tool")
        args = step.get("args") if isinstance(step.get("args"), dict) else {}

        # 1. Protected-path DENY: only meaningful for file-writing tools.
        if tool in WRITE_TOOLS:
            path = step_path(args)
            if self._config.matches_protected_path(path):
                return PolicyVerdict(
                    Decision.DENY,
                    reason=f"Writes to a protected path ({path}) are denied by policy.",
                    rule="protected_path",
                )

        # 2. Most restrictive action across the step's alerts.
        if ctx.alerts:
            actions: list[Action] = [
                self._config.action_for_rule(alert.rule, alert.severity)
                for alert in ctx.alerts
            ]
            action = most_restrictive(actions)
            decision = _ACTION_TO_DECISION[action]
            # Attribute the verdict to the alert whose action drove it.
            driving = next(
                (
                    a
                    for a in ctx.alerts
                    if self._config.action_for_rule(a.rule, a.severity) == action
                ),
                ctx.alerts[0],
            )
            if decision is Decision.ALLOW:
                reason = "phase2: allowed (recorded)"
            else:
                verb = "denied" if decision is Decision.DENY else "needs approval"
                reason = f"{driving.title} — {verb} by policy."
            return PolicyVerdict(decision, reason=reason, rule=driving.rule)

        # 3. Nothing flagged.
        return PolicyVerdict(Decision.ALLOW, reason="phase2: no policy match")
