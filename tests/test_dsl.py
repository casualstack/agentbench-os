"""Tests for eval DSL validation."""

from __future__ import annotations

import pytest

from agentbench.dsl.validator import ValidationError, validate_oracle, validate_task_dict


def test_validate_task_dict_accepts_minimal_valid_task():
    validate_task_dict(
        {
            "id": "sample",
            "name": "Sample",
            "description": "desc",
            "prompt": "do thing",
            "workspace": {"main.py": "print('hi')\n"},
            "oracles": [{"type": "no_network"}],
        }
    )


def test_validate_task_dict_rejects_missing_fields():
    with pytest.raises(ValidationError, match="missing required fields"):
        validate_task_dict({"id": "x"})


def test_validate_oracle_rejects_unknown_type():
    with pytest.raises(ValidationError, match="unknown type"):
        validate_oracle({"type": "magic_wand"})


def test_validate_oracle_requires_params():
    with pytest.raises(ValidationError, match="missing required param: command"):
        validate_oracle({"type": "test_must_pass"})
