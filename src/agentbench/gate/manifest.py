"""Load task manifest files for gated / matrix runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_task_manifest(path: Path | str) -> list[str]:
    """Return task file names from a manifest JSON."""
    manifest_path = Path(path)
    data = _read_manifest(manifest_path)

    subset_ref = data.get("task_subset")
    if subset_ref:
        subset_path = (manifest_path.parent / subset_ref).resolve()
        return load_task_manifest(subset_path)

    task_files = data.get("task_files")
    if not isinstance(task_files, list) or not task_files:
        raise ValueError(f"{manifest_path}: manifest must include non-empty task_files")
    return [str(name) for name in task_files]


def _read_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: manifest must be a JSON object")
    return data
