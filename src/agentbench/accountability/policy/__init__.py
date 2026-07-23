"""Phase 2 policy seam -- design-only skeleton, no enforcement engine (Phase 1).

Exposes the Decision/PolicyContext/PolicyVerdict/PolicyEngine types so
Phase 2 can slot in a real engine without touching call sites again.
``ObservePolicyEngine`` is the only implementation Phase 1 ships: it
always ALLOWs, wired into ``SessionWatcher`` as a no-op pass-through.
"""

from agentbench.accountability.policy.config import (
    PolicyConfig,
    PolicyConfigError,
    load_policy,
)
from agentbench.accountability.policy.decision import Decision, PolicyContext, PolicyVerdict
from agentbench.accountability.policy.engine import (
    ConfigPolicyEngine,
    ObservePolicyEngine,
    PolicyEngine,
)

__all__ = [
    "ConfigPolicyEngine",
    "Decision",
    "ObservePolicyEngine",
    "PolicyConfig",
    "PolicyConfigError",
    "PolicyContext",
    "PolicyEngine",
    "PolicyVerdict",
    "load_policy",
]
