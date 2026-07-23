"""Tests for loading and validating ``.agentbench/policy.yml``."""

from __future__ import annotations

import pytest

from agentbench.accountability.policy.config import (
    PolicyConfig,
    PolicyConfigError,
    load_policy,
    most_restrictive,
)


def test_defaults_are_sensible():
    cfg = PolicyConfig()
    assert cfg.version == 1
    assert cfg.action_for_severity("critical") == "ask"
    assert cfg.action_for_severity("warning") == "allow"
    assert cfg.on_error == "allow"
    assert cfg.rules == {}
    assert cfg.protected_paths == []


def test_extra_top_level_keys_rejected():
    with pytest.raises(Exception):
        PolicyConfig.model_validate({"version": 1, "bogus": True})


def test_invalid_action_rejected():
    with pytest.raises(Exception):
        PolicyConfig.model_validate({"rules": {"secret_file_write": "nuke"}})


def test_rule_override_beats_severity_default():
    cfg = PolicyConfig(defaults={"critical": "ask"}, rules={"secret_file_write": "deny"})
    assert cfg.action_for_rule("secret_file_write", "critical") == "deny"
    # A critical rule with no override falls back to the severity default.
    assert cfg.action_for_rule("destructive_command", "critical") == "ask"


@pytest.mark.parametrize(
    "path,expected",
    [
        (".env", True),
        (".env.local", True),
        ("/home/u/proj/.env.production", True),
        ("C:\\work\\proj\\.env", True),
        (".github/workflows/ci.yml", True),
        ("/home/u/proj/.github/workflows/release.yml", True),
        ("src/app.py", False),
        ("environment.py", False),
        (None, False),
    ],
)
def test_protected_path_matching(path, expected):
    cfg = PolicyConfig(protected_paths=[".env*", ".github/workflows/**"])
    assert cfg.matches_protected_path(path) is expected


def test_most_restrictive():
    assert most_restrictive([]) == "allow"
    assert most_restrictive(["allow", "ask"]) == "ask"
    assert most_restrictive(["ask", "deny", "allow"]) == "deny"
    assert most_restrictive(["allow", "allow"]) == "allow"


def test_load_policy_none_when_absent(tmp_path):
    assert load_policy(project_root=tmp_path, home=tmp_path) is None


def test_load_policy_prefers_project_over_home(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    (home / ".agentbench").mkdir(parents=True)
    (project / ".agentbench").mkdir(parents=True)
    (home / ".agentbench" / "policy.yml").write_text("rules:\n  secret_file_write: allow\n")
    (project / ".agentbench" / "policy.yml").write_text("rules:\n  secret_file_write: deny\n")

    cfg = load_policy(project_root=project, home=home)
    assert cfg is not None
    assert cfg.rules["secret_file_write"] == "deny"


def test_load_policy_falls_back_to_home(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    project.mkdir()
    (home / ".agentbench").mkdir(parents=True)
    (home / ".agentbench" / "policy.yml").write_text("on_error: deny\n")

    cfg = load_policy(project_root=project, home=home)
    assert cfg is not None
    assert cfg.on_error == "deny"


def test_load_policy_malformed_raises(tmp_path):
    (tmp_path / ".agentbench").mkdir()
    (tmp_path / ".agentbench" / "policy.yml").write_text("rules:\n  x: not-an-action\n")
    with pytest.raises(PolicyConfigError):
        load_policy(project_root=tmp_path, home=tmp_path)


def test_load_policy_empty_file_is_valid(tmp_path):
    (tmp_path / ".agentbench").mkdir()
    (tmp_path / ".agentbench" / "policy.yml").write_text("")
    cfg = load_policy(project_root=tmp_path, home=tmp_path)
    assert cfg is not None
    assert cfg.version == 1
