"""Oracle: a shell command (typically pytest) must exit with code 0."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from agentbench.models.task import Oracle, OracleResult
from agentbench.oracles.base import OracleCheck, register_oracle
from agentbench.core.trajectory import Trajectory


def _resolve_command(command: str) -> str:
    """Use the current interpreter when tasks invoke `python`."""
    if command == "python":
        return sys.executable
    if command.startswith("python "):
        return f"{sys.executable}{command[6:]}"
    return command


@register_oracle
class TestMustPassOracle(OracleCheck):
    oracle_type = "test_must_pass"

    def check(
        self,
        oracle: Oracle,
        workspace: Path,
        trajectory: Trajectory,
        initial_workspace: dict[str, str],
    ) -> OracleResult:
        command = _resolve_command(oracle.params.get("command", ""))
        if not command:
            return OracleResult(
                oracle_type=self.oracle_type,
                passed=False,
                message="Missing required param: command",
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=oracle.params.get("timeout", 60),
            )
        except subprocess.TimeoutExpired:
            return OracleResult(
                oracle_type=self.oracle_type,
                passed=False,
                message=f"Command timed out: {command}",
            )

        if result.returncode == 0:
            return OracleResult(
                oracle_type=self.oracle_type,
                passed=True,
                message=f"Command passed: {command}",
            )

        stderr = result.stderr.strip() or result.stdout.strip()
        snippet = stderr[:500] if stderr else "(no output)"
        return OracleResult(
            oracle_type=self.oracle_type,
            passed=False,
            message=f"Command failed (exit {result.returncode}): {command} — {snippet.splitlines()[0] if snippet else '(no output)'}",
            details={"stderr": snippet, "returncode": result.returncode},
        )
