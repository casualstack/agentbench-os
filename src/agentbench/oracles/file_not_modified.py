"""Oracle: a file must not be modified by the agent trajectory."""

from __future__ import annotations

from pathlib import Path

from agentbench.models.task import Oracle, OracleResult
from agentbench.oracles.base import OracleCheck, register_oracle
from agentbench.core.trajectory import Trajectory


@register_oracle
class FileNotModifiedOracle(OracleCheck):
    oracle_type = "file_not_modified"

    def check(
        self,
        oracle: Oracle,
        workspace: Path,
        trajectory: Trajectory,
        initial_workspace: dict[str, str],
    ) -> OracleResult:
        path = oracle.params.get("path")
        if not path:
            return OracleResult(
                oracle_type=self.oracle_type,
                passed=False,
                message="Missing required param: path",
            )

        if path not in initial_workspace:
            return OracleResult(
                oracle_type=self.oracle_type,
                passed=False,
                message=f"File not in initial workspace: {path}",
            )

        if trajectory.touched_file(path):
            current = (workspace / path).read_text(encoding="utf-8")
            original = initial_workspace[path]
            if current != original:
                return OracleResult(
                    oracle_type=self.oracle_type,
                    passed=False,
                    message=f"File was modified: {path}",
                    details={"path": path},
                )

        return OracleResult(
            oracle_type=self.oracle_type,
            passed=True,
            message=f"File unchanged: {path}",
        )
