"""Oracle: a file must contain a required assertion pattern."""

from __future__ import annotations

import re
from pathlib import Path

from agentbench.eval.models import Oracle, OracleResult
from agentbench.eval.oracles.base import OracleCheck, register_oracle
from agentbench.core.trajectory import Trajectory


@register_oracle
class AssertionExistsOracle(OracleCheck):
    oracle_type = "assertion_exists"

    def check(
        self,
        oracle: Oracle,
        workspace: Path,
        trajectory: Trajectory,
        initial_workspace: dict[str, str],
    ) -> OracleResult:
        path = oracle.params.get("path")
        pattern = oracle.params.get("pattern")
        if not path or not pattern:
            return OracleResult(
                oracle_type=self.oracle_type,
                passed=False,
                message="Missing required params: path and pattern",
            )

        file_path = workspace / path
        if not file_path.exists():
            return OracleResult(
                oracle_type=self.oracle_type,
                passed=False,
                message=f"File not found: {path}",
            )

        content = file_path.read_text(encoding="utf-8")
        if re.search(pattern, content, re.MULTILINE):
            return OracleResult(
                oracle_type=self.oracle_type,
                passed=True,
                message=f"Assertion pattern found in {path}",
            )

        return OracleResult(
            oracle_type=self.oracle_type,
            passed=False,
            message=f"Assertion pattern missing in {path}: {pattern!r}",
            details={"path": path, "pattern": pattern},
        )
