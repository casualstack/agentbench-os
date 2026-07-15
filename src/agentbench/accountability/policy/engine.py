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

from agentbench.accountability.policy.decision import Decision, PolicyContext, PolicyVerdict


class PolicyEngine(ABC):
    """Decides what should happen to one step. Phase 1 never acts on this."""

    @abstractmethod
    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict:
        ...


class ObservePolicyEngine(PolicyEngine):
    """Phase 1 default. Always ALLOW -- accountability only, no enforcement."""

    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict:
        return PolicyVerdict(Decision.ALLOW, reason="phase1: observe-only")
