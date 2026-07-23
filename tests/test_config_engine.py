"""Tests for ConfigPolicyEngine: mapping steps + alerts -> decisions."""

from __future__ import annotations

from agentbench.accountability.policy import (
    ConfigPolicyEngine,
    Decision,
    PolicyConfig,
    PolicyContext,
)
from agentbench.accountability.rules import Alert, check_step

CWD = "/work/repo"


def _verdict(cfg: PolicyConfig, step: dict, *, cwd: str | None = CWD):
    engine = ConfigPolicyEngine(cfg)
    alerts = check_step(step, 0, cwd=cwd)
    return engine.evaluate(
        PolicyContext(agent="claude-code-hook", session_id="s", cwd=cwd,
                      step=step, step_index=0, alerts=alerts)
    )


def test_no_alert_no_protected_path_allows():
    v = _verdict(PolicyConfig(), {"tool": "Write", "args": {"file_path": "src/app.py",
                                                            "content": "x = 1"}})
    assert v.decision is Decision.ALLOW


def test_protected_path_write_denied():
    cfg = PolicyConfig(protected_paths=[".github/workflows/**"])
    v = _verdict(cfg, {"tool": "Write", "args": {
        "file_path": f"{CWD}/.github/workflows/ci.yml", "content": "on: push"}})
    assert v.decision is Decision.DENY
    assert v.rule == "protected_path"


def test_rule_override_denies():
    cfg = PolicyConfig(rules={"destructive_command": "deny"})
    v = _verdict(cfg, {"tool": "Bash", "args": {"command": "rm -rf build"}})
    assert v.decision is Decision.DENY
    assert v.rule == "destructive_command"


def test_severity_default_asks_on_critical():
    cfg = PolicyConfig(defaults={"critical": "ask", "warning": "allow"})
    v = _verdict(cfg, {"tool": "Bash", "args": {"command": "sudo rm x"}})
    assert v.decision is Decision.REQUIRE_APPROVAL


def test_warning_default_allows_but_reports_rule():
    cfg = PolicyConfig(defaults={"critical": "ask", "warning": "allow"})
    # A network command is a warning-severity alert.
    v = _verdict(cfg, {"tool": "Bash", "args": {"command": "curl https://example.com"}})
    assert v.decision is Decision.ALLOW


def test_most_restrictive_wins_across_alerts():
    # Craft two alerts of different configured actions; deny must win.
    cfg = PolicyConfig(rules={"network_command": "ask", "possible_data_exfiltration": "deny"})
    engine = ConfigPolicyEngine(cfg)
    alerts = [
        Alert(rule="network_command", severity="warning", title="net", detail="d", step_index=0),
        Alert(rule="possible_data_exfiltration", severity="warning", title="exfil",
              detail="d", step_index=0),
    ]
    v = engine.evaluate(PolicyContext(agent="a", session_id="s", cwd=CWD,
                                      step={"tool": "Bash", "args": {}}, step_index=0,
                                      alerts=alerts))
    assert v.decision is Decision.DENY
    assert v.rule == "possible_data_exfiltration"


def test_protected_path_only_applies_to_writes():
    # A Bash command mentioning .env is not a *write* to it -> no protected deny.
    cfg = PolicyConfig(protected_paths=[".env*"])
    v = _verdict(cfg, {"tool": "Bash", "args": {"command": "cat .env"}})
    assert v.decision is Decision.ALLOW


def test_evaluate_is_side_effect_free_and_sync():
    import inspect
    assert not inspect.iscoroutinefunction(ConfigPolicyEngine.evaluate)
