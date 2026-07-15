"""Base oracle interface and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from agentbench.eval.models import Oracle, OracleResult

if TYPE_CHECKING:
    from agentbench.core.trajectory import Trajectory


class OracleCheck(ABC):
    """Abstract oracle that inspects workspace + trajectory."""

    oracle_type: str

    @abstractmethod
    def check(
        self,
        oracle: Oracle,
        workspace: Path,
        trajectory: Trajectory,
        initial_workspace: dict[str, str],
    ) -> OracleResult:
        ...


_REGISTRY: dict[str, type[OracleCheck]] = {}


def register_oracle(cls: type[OracleCheck]) -> type[OracleCheck]:
    _REGISTRY[cls.oracle_type] = cls
    return cls


def get_oracle(oracle_type: str) -> OracleCheck:
    if oracle_type not in _REGISTRY:
        raise ValueError(
            f"Unknown oracle type: {oracle_type!r}. "
            f"Known types: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[oracle_type]()
