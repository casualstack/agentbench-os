"""Tests for the Claude Code PreToolUse hook (accountability.hook)."""

from __future__ import annotations

import json

from agentbench.accountability.audit import AuditStore
from agentbench.accountability.hook import run_hook
from agentbench.accountability.policy import (
    ConfigPolicyEngine,
    Decision,
    PolicyConfig,
    PolicyContext,
    PolicyEngine,
    PolicyVerdict,
)


def _payload(tool_name: str, tool_input: dict, *, cwd="/work/repo", session_id="s1") -> str:
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": cwd,
        "session_id": session_id,
    })


def _decision(stdout: str) -> str | None:
    if not stdout:
        return None
    return json.loads(stdout)["hookSpecificOutput"]["permissionDecision"]


def test_deny_destructive_command():
    engine = ConfigPolicyEngine(PolicyConfig(rules={"destructive_command": "deny"}))
    res = run_hook(_payload("Bash", {"command": "rm -rf build"}), engine=engine, record=False)
    assert res.exit_code == 0
    assert _decision(res.stdout) == "deny"


def test_ask_on_protected_path_write():
    engine = ConfigPolicyEngine(PolicyConfig(protected_paths=[".env*"]))
    res = run_hook(
        _payload("Write", {"file_path": "/work/repo/.env", "content": "SECRET=1"}),
        engine=engine, record=False,
    )
    assert _decision(res.stdout) == "deny"


def test_benign_read_stays_out_of_the_way():
    engine = ConfigPolicyEngine(PolicyConfig())
    res = run_hook(_payload("Read", {"file_path": "README.md"}), engine=engine, record=False)
    assert res.exit_code == 0
    assert res.stdout == ""  # ALLOW -> no output, normal permission flow


def test_edit_maps_to_str_replace_and_flags_weakened_assertion():
    engine = ConfigPolicyEngine(PolicyConfig(rules={"weakened_assertion": "deny"}))
    res = run_hook(
        _payload("Edit", {
            "file_path": "tests/test_x.py",
            "old_string": "assert result == 42",
            "new_string": "assert True",
        }),
        engine=engine, record=False,
    )
    assert _decision(res.stdout) == "deny"


def test_malformed_stdin_fails_open():
    res = run_hook("not json at all", record=False)
    assert res.exit_code == 0
    assert res.stdout == ""


def test_empty_stdin_fails_open():
    res = run_hook("", record=False)
    assert res.exit_code == 0
    assert res.stdout == ""


class _ExplodingEngine(PolicyEngine):
    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict:
        raise RuntimeError("boom")


def test_engine_error_fails_open():
    res = run_hook(_payload("Bash", {"command": "rm -rf /"}),
                   engine=_ExplodingEngine(), record=False)
    assert res.exit_code == 0
    assert res.stdout == ""  # never wedge the agent on our own bug


class _ExplodingFailClosedEngine(PolicyEngine):
    on_error = "deny"

    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict:
        raise RuntimeError("boom")


def test_engine_error_can_fail_closed():
    res = run_hook(_payload("Bash", {"command": "rm -rf /"}),
                   engine=_ExplodingFailClosedEngine(), record=False)
    assert res.exit_code == 0  # still never crash
    assert _decision(res.stdout) == "deny"  # but block when asked to fail closed


def test_config_engine_reports_on_error():
    from agentbench.accountability.policy import ConfigPolicyEngine, PolicyConfig
    assert ConfigPolicyEngine(PolicyConfig(on_error="deny")).on_error == "deny"
    assert ConfigPolicyEngine(PolicyConfig()).on_error == "allow"


def test_records_decision_to_audit_trail(tmp_path):
    db = tmp_path / "audit.db"
    engine = ConfigPolicyEngine(PolicyConfig(rules={"destructive_command": "deny"}))
    res = run_hook(
        _payload("Bash", {"command": "git push --force"}),
        engine=engine, audit_db=db, record=True,
    )
    assert _decision(res.stdout) == "deny"

    store = AuditStore(db)
    try:
        events = list(store.iter_events())
        assert store.verify() is None  # chain intact
    finally:
        store.close()

    assert len(events) == 1
    ev = events[0]
    assert ev["agent"] == "claude-code-hook"
    assert ev["rule"] == "destructive_command"
    assert "[Blocked]" in ev["title"]
    assert "Enforcement decision: deny" in ev["detail"]


def test_observe_only_records_alert_but_allows(tmp_path):
    # No policy engine passed AND no policy.yml under home -> observe-only.
    db = tmp_path / "audit.db"
    res = run_hook(
        _payload("Bash", {"command": "rm -rf build"}),
        home=tmp_path, audit_db=db, record=True,
    )
    # Observe-only: allowed (no output) but the alert is still recorded.
    assert res.stdout == ""
    store = AuditStore(db)
    try:
        events = list(store.iter_events())
    finally:
        store.close()
    assert len(events) == 1
    assert events[0]["rule"] == "destructive_command"
    assert "[Allowed]" in events[0]["title"]


def test_benign_step_records_nothing(tmp_path):
    db = tmp_path / "audit.db"
    run_hook(_payload("Read", {"file_path": "x"}), home=tmp_path, audit_db=db, record=True)
    # AuditStore lazily creates the file; assert no rows regardless.
    store = AuditStore(db)
    try:
        assert list(store.iter_events()) == []
    finally:
        store.close()
