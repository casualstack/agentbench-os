"""Oracle: agent trajectory must not include network access."""

from __future__ import annotations

from pathlib import Path

from agentbench.models.task import Oracle, OracleResult
from agentbench.oracles.base import OracleCheck, register_oracle
from agentbench.core.trajectory import Trajectory

_NETWORK_PATTERNS = (
    "curl",
    "wget",
    "fetch(",
    "http://",
    "https://",
    "requests.",
    "urllib",
    "httpx",
    "socket.",
    "webbrowser",
    # Package managers reaching a registry
    "pip install",
    "npm install",
    "npm ci",
    "pnpm install",
    "pnpm add",
    "yarn install",
    "yarn add",
    "bun install",
    "bun add",
    "cargo add",
    "cargo install",
    "go get",
    "go install",
)


@register_oracle
class NoNetworkOracle(OracleCheck):
    oracle_type = "no_network"

    def check(
        self,
        oracle: Oracle,
        workspace: Path,
        trajectory: Trajectory,
        initial_workspace: dict[str, str],
    ) -> OracleResult:
        violations = trajectory.find_network_violations(_NETWORK_PATTERNS)
        if violations:
            first = violations[0]
            return OracleResult(
                oracle_type=self.oracle_type,
                passed=False,
                message=f"Network access detected in step {first['step_index']}: {first['match']}",
                details={"violations": violations},
            )

        return OracleResult(
            oracle_type=self.oracle_type,
            passed=True,
            message="No network access detected in trajectory",
        )
