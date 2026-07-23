"""Eval DSL validation for task and trajectory JSON documents."""

from __future__ import annotations

from typing import Any

from agentbench.core.trajectory import ValidationError, validate_trajectory_dict

KNOWN_ORACLE_TYPES = frozenset(
    {
        "test_must_pass",
        "file_not_modified",
        "no_network",
        "assertion_exists",
    }
)

TASK_REQUIRED_FIELDS = ("id", "name", "description", "prompt", "workspace", "oracles")
ORACLE_REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "test_must_pass": ("command",),
    "file_not_modified": ("path",),
    "no_network": (),
    "assertion_exists": ("path", "pattern"),
}


def validate_oracle(data: dict[str, Any], *, index: int | None = None) -> None:
    prefix = f"oracles[{index}]" if index is not None else "oracle"
    if not isinstance(data, dict):
        raise ValidationError(f"{prefix} must be an object")

    oracle_type = data.get("type")
    if not oracle_type:
        raise ValidationError(f"{prefix} missing required field: type")
    if oracle_type not in KNOWN_ORACLE_TYPES:
        raise ValidationError(
            f"{prefix} has unknown type {oracle_type!r}; "
            f"known: {sorted(KNOWN_ORACLE_TYPES)}"
        )

    for param in ORACLE_REQUIRED_PARAMS[oracle_type]:
        if param not in data:
            raise ValidationError(
                f"{prefix} type={oracle_type!r} missing required param: {param}"
            )


def validate_task_dict(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValidationError("task must be a JSON object")

    missing = [field for field in TASK_REQUIRED_FIELDS if field not in data]
    if missing:
        raise ValidationError(f"task missing required fields: {missing}")

    workspace = data["workspace"]
    if not isinstance(workspace, dict) or not workspace:
        raise ValidationError("task.workspace must be a non-empty object")
    for path, content in workspace.items():
        if not isinstance(path, str) or not path.strip():
            raise ValidationError("task.workspace keys must be non-empty strings")
        if not isinstance(content, str):
            raise ValidationError(f"task.workspace[{path!r}] must be a string")

    oracles = data["oracles"]
    if not isinstance(oracles, list) or not oracles:
        raise ValidationError("task.oracles must be a non-empty array")
    for i, oracle in enumerate(oracles):
        validate_oracle(oracle, index=i)

    tags = data.get("tags", [])
    if tags is not None and not isinstance(tags, list):
        raise ValidationError("task.tags must be an array when present")
