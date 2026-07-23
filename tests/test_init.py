"""Tests for ``agentbench init`` install helpers (accountability.install)."""

from __future__ import annotations

import json

from agentbench.accountability.install import (
    HOOK_COMMAND,
    install_hook,
    merge_hook_settings,
    scaffold_policy,
)


def test_merge_into_empty_settings_adds_hook():
    merged, changed = merge_hook_settings({})
    assert changed is True
    groups = merged["hooks"]["PreToolUse"]
    assert any(
        h.get("command") == HOOK_COMMAND
        for g in groups for h in g.get("hooks", [])
    )


def test_merge_is_idempotent():
    once, _ = merge_hook_settings({})
    twice, changed = merge_hook_settings(once)
    assert changed is False
    assert twice == once


def test_merge_preserves_existing_hooks_and_settings():
    existing = {
        "model": "opus",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-tool"}]}
            ],
            "PostToolUse": [{"matcher": "*", "hooks": []}],
        },
    }
    merged, changed = merge_hook_settings(existing)
    assert changed is True
    assert merged["model"] == "opus"
    assert "PostToolUse" in merged["hooks"]
    commands = [
        h.get("command")
        for g in merged["hooks"]["PreToolUse"] for h in g.get("hooks", [])
    ]
    assert "other-tool" in commands
    assert HOOK_COMMAND in commands


def test_install_hook_writes_file(tmp_path):
    assert install_hook(tmp_path) is True
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert settings["hooks"]["PreToolUse"]
    # Second run is a no-op.
    assert install_hook(tmp_path) is False


def test_install_hook_preserves_unrelated_settings_on_disk(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"permissions": {"allow": ["Read"]}}))
    install_hook(tmp_path)
    settings = json.loads(settings_path.read_text())
    assert settings["permissions"] == {"allow": ["Read"]}
    assert settings["hooks"]["PreToolUse"]


def test_scaffold_policy_creates_once(tmp_path):
    assert scaffold_policy(tmp_path) is True
    policy = tmp_path / ".agentbench" / "policy.yml"
    assert policy.is_file()
    assert "version: 1" in policy.read_text()
    # Doesn't overwrite an existing policy.
    policy.write_text("version: 1\non_error: deny\n")
    assert scaffold_policy(tmp_path) is False
    assert "on_error: deny" in policy.read_text()


def test_scaffolded_policy_is_valid():
    from agentbench.accountability.policy import load_policy

    # Round-trip: what we scaffold must parse cleanly.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        scaffold_policy(d)
        cfg = load_policy(project_root=Path(d), home=Path(d))
        assert cfg is not None
        assert cfg.rules.get("secret_file_write") == "deny"
