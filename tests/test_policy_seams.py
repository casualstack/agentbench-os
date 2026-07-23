"""Tests for the Phase 2 policy seam types and their (no-op) wiring into
SessionWatcher.

Phase 1 ships exactly one engine -- ObservePolicyEngine, which always
ALLOWs -- wired into the watch poll loop as a pass-through whose verdict
is discarded, never acted on. These tests prove the seam types work in
isolation and that wiring the engine into SessionWatcher doesn't change
any observable behavior.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from agentbench.accountability.policy import (
    Decision,
    ObservePolicyEngine,
    PolicyContext,
    PolicyEngine,
    PolicyVerdict,
)
from agentbench.accountability.rules import Alert, check_step
from agentbench.accountability.watcher import SessionWatcher

CWD = "C:\\work\\myrepo"


def _session_line(tool: str, args: dict, *, model: str = "claude-sonnet-5") -> str:
    return json.dumps(
        {
            "type": "assistant",
            "cwd": CWD,
            "version": "2.1.0",
            "message": {
                "model": model,
                "content": [{"type": "tool_use", "name": tool, "input": args}],
            },
        }
    )


def _write_session(root: Path, name: str, lines: list[str]) -> Path:
    project = root / ".claude" / "projects" / "C--work-myrepo"
    project.mkdir(parents=True, exist_ok=True)
    path = project / f"{name}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# -- seam types in isolation --------------------------------------------------


def test_decision_has_three_values():
    assert {d.value for d in Decision} == {"allow", "deny", "require_approval"}


def test_policy_context_constructs():
    ctx = PolicyContext(
        agent="claude-code",
        session_id="s1",
        cwd=CWD,
        step={"tool": "Bash", "args": {"command": "ls"}},
        step_index=0,
        alerts=[],
    )
    assert ctx.agent == "claude-code"
    assert ctx.step == {"tool": "Bash", "args": {"command": "ls"}}
    assert ctx.alerts == []


def test_policy_verdict_constructs():
    verdict = PolicyVerdict(decision=Decision.DENY, reason="test", rule="some_rule")
    assert verdict.decision == Decision.DENY
    assert verdict.reason == "test"
    assert verdict.rule == "some_rule"


def test_policy_verdict_rule_defaults_to_none():
    verdict = PolicyVerdict(decision=Decision.ALLOW, reason="ok")
    assert verdict.rule is None


def test_policy_engine_is_abstract():
    with pytest.raises(TypeError):
        PolicyEngine()  # type: ignore[abstract]


def test_observe_policy_engine_always_allows():
    engine = ObservePolicyEngine()
    ctx = PolicyContext(
        agent="claude-code",
        session_id="s1",
        cwd=CWD,
        step={"tool": "run_command", "args": {"command": "rm -rf /"}},
        step_index=0,
        alerts=[
            Alert(
                rule="destructive_command",
                severity="critical",
                title="Ran a destructive command",
                detail="detail",
                step_index=0,
            )
        ],
    )
    verdict = engine.evaluate(ctx)
    assert verdict.decision == Decision.ALLOW
    assert verdict.reason == "phase1: observe-only"


def test_observe_policy_engine_evaluate_is_synchronous():
    # Seam requirement: evaluate() must stay synchronous, not a coroutine --
    # a future hook adapter needs this inside a tight latency budget.
    assert not inspect.iscoroutinefunction(ObservePolicyEngine.evaluate)


# -- wired into SessionWatcher: zero observable behavior change --------------


class _RecordingPolicyEngine(PolicyEngine):
    """Spy engine: always ALLOWs (matching ObservePolicyEngine) but records
    every context it was asked to evaluate, so the test can assert the
    watcher actually calls it once per step."""

    def __init__(self) -> None:
        self.contexts: list[PolicyContext] = []

    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict:
        self.contexts.append(ctx)
        return PolicyVerdict(Decision.ALLOW, reason="recording")


def test_session_watcher_defaults_to_observe_policy_engine():
    watcher = SessionWatcher()
    assert isinstance(watcher._policy_engine, ObservePolicyEngine)


def test_session_watcher_invokes_policy_engine_once_per_step(tmp_path):
    _write_session(
        tmp_path,
        "s1",
        [
            _session_line("Bash", {"command": "ls"}),
            _session_line("Bash", {"command": "pytest -q"}),
        ],
    )
    spy = _RecordingPolicyEngine()
    watcher = SessionWatcher(home=tmp_path, policy_engine=spy)
    watcher.poll()

    assert len(spy.contexts) == 2
    assert [c.step_index for c in spy.contexts] == [0, 1]
    assert all(c.agent == "claude-code" for c in spy.contexts)
    assert all(c.cwd == CWD for c in spy.contexts)


def test_wiring_policy_engine_changes_zero_observable_behavior(tmp_path):
    _write_session(
        tmp_path,
        "s1",
        [
            _session_line(
                "Edit",
                {
                    "file_path": "tests/test_app.py",
                    "old_string": "assert x == 1",
                    "new_string": "pass",
                },
            ),
            _session_line("Bash", {"command": "rm -rf /tmp/x"}),
        ],
    )

    default_watcher = SessionWatcher(home=tmp_path)
    default_events = default_watcher.poll()

    spy = _RecordingPolicyEngine()
    spied_watcher = SessionWatcher(home=tmp_path, policy_engine=spy)
    spied_events = spied_watcher.poll()

    def _shape(events):
        return [
            (
                e.agent,
                e.session_id,
                e.cwd,
                e.model,
                e.new_steps,
                [(a.rule, a.severity, a.title, a.detail, a.step_index, a.path) for a in e.alerts],
            )
            for e in events
        ]

    assert _shape(default_events) == _shape(spied_events)
    assert len(spy.contexts) == 2  # policy engine still ran, just discarded


# -- locked transport-agnostic shape (seam requirement #2) -------------------


def test_check_step_signature_is_transport_agnostic():
    sig = inspect.signature(check_step)
    params = list(sig.parameters.values())
    assert params[0].name == "step"
    assert params[1].name == "step_index"
    assert params[2].name == "cwd"
    assert params[2].kind == inspect.Parameter.KEYWORD_ONLY
    assert params[2].default is None


def test_check_step_accepts_plain_dict_step():
    # No SessionWatcher/adapter-specific object required -- a hook-based
    # interception adapter could build this dict directly.
    alerts = check_step(
        {"tool": "run_command", "args": {"command": "rm -rf /tmp/x"}},
        0,
        cwd=CWD,
    )
    assert any(a.rule == "destructive_command" for a in alerts)
