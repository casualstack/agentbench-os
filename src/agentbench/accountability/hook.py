"""Claude Code PreToolUse hook: the enforcement entry point.

Claude Code can run a command before every tool call and let that command
allow, block, or force-approve the call. ``agentbench init`` registers
``agentbench hook`` as that command; this module is what runs.

Flow, per invocation (one child process per tool call):

1. Read Claude Code's PreToolUse JSON from stdin.
2. Normalize ``tool_name``/``tool_input`` into AgentBench's ``{tool, args}``
   step vocabulary (``core.steps``) -- the same shape ``rules.check_step`` and
   ``PolicyEngine.evaluate`` already consume.
3. Run the zero-config rules, then the policy engine loaded from
   ``.agentbench/policy.yml`` (observe-only if none exists).
4. Record the decision to the hash-chained audit trail (best-effort).
5. Emit Claude Code's permission decision (allow / ask / deny).

Fail-safe: any error is caught and turned into an *allow* (or the config's
``on_error`` if we got that far), so a bug here can never wedge the agent.
The decision mapping onto Claude Code's contract:

* ALLOW            -> stay out of the way (no output; normal permission flow)
* REQUIRE_APPROVAL -> ``permissionDecision: "ask"`` (force a human prompt)
* DENY             -> ``permissionDecision: "deny"`` (block, with a reason)
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentbench.accountability.policy import (
    ConfigPolicyEngine,
    Decision,
    ObservePolicyEngine,
    PolicyConfigError,
    PolicyContext,
    PolicyEngine,
    load_policy,
)
from agentbench.accountability.rules import Alert, check_step

AGENT = "claude-code-hook"


@dataclass
class HookResult:
    exit_code: int
    stdout: str


def _normalize_tool_call(tool_name: str, tool_input: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a Claude Code tool call to zero or more normalized steps.

    Claude Code's tool names differ from AgentBench's vocabulary, so translate
    the ones that write files or run commands; anything else passes through and
    simply won't match any write/run rule.
    """
    ti = tool_input if isinstance(tool_input, dict) else {}

    if tool_name == "Write":
        return [{"tool": "Write", "args": {"file_path": ti.get("file_path"),
                                           "content": ti.get("content")}}]
    if tool_name == "Edit":
        return [{"tool": "StrReplace", "args": {
            "file_path": ti.get("file_path"),
            "old_string": ti.get("old_string"),
            "new_string": ti.get("new_string"),
        }}]
    if tool_name == "MultiEdit":
        steps: list[dict[str, Any]] = []
        for edit in ti.get("edits") or []:
            if not isinstance(edit, dict):
                continue
            steps.append({"tool": "StrReplace", "args": {
                "file_path": ti.get("file_path"),
                "old_string": edit.get("old_string"),
                "new_string": edit.get("new_string"),
            }})
        return steps or [{"tool": "StrReplace", "args": {"file_path": ti.get("file_path")}}]
    if tool_name == "NotebookEdit":
        return [{"tool": "Write", "args": {"file_path": ti.get("notebook_path"),
                                           "content": ti.get("new_source")}}]
    if tool_name == "Bash":
        return [{"tool": "Bash", "args": {"command": ti.get("command")}}]

    # Read/Glob/Grep/etc: not a write or run tool -- no rule applies.
    return [{"tool": tool_name, "args": ti}]


def _build_engine(cwd: str | None, home: Path | None) -> tuple[PolicyEngine, str | None]:
    """Load the policy engine for this cwd, or observe-only. Second element is
    a non-fatal warning to surface (e.g. malformed config)."""
    try:
        config = load_policy(project_root=cwd, home=home)
    except PolicyConfigError as exc:
        # Malformed policy: fail open (observe-only) but tell the user loudly.
        return ObservePolicyEngine(), str(exc)
    if config is None:
        return ObservePolicyEngine(), None
    return ConfigPolicyEngine(config), None


_RANK = {Decision.ALLOW: 0, Decision.REQUIRE_APPROVAL: 1, Decision.DENY: 2}


def _permission_output(decision: Decision, reason: str) -> str:
    """Claude Code PreToolUse hook JSON, or empty string to stay out of the way."""
    if decision is Decision.ALLOW:
        return ""
    mapping = {Decision.DENY: "deny", Decision.REQUIRE_APPROVAL: "ask"}
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": mapping[decision],
            "permissionDecisionReason": reason,
        }
    })


def run_hook(
    stdin_text: str,
    *,
    home: Path | None = None,
    audit_db: Path | str | None = None,
    engine: PolicyEngine | None = None,
    record: bool = True,
) -> HookResult:
    """Evaluate one PreToolUse payload and return the decision.

    ``engine``/``audit_db``/``home`` are injectable for testing. Never raises:
    on any unexpected error it fails open (allow) so the agent is never wedged.
    """
    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
    except json.JSONDecodeError:
        return HookResult(0, "")  # can't parse -> stay out of the way

    if not isinstance(payload, dict):
        return HookResult(0, "")

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd")
    session_id = payload.get("session_id") or "unknown"

    on_error = "allow"
    try:
        active_engine, warning = (engine, None) if engine is not None else _build_engine(cwd, home)
        on_error = getattr(active_engine, "on_error", "allow")
        if warning:
            print(f"[agentbench] {warning}", file=sys.stderr)

        steps = _normalize_tool_call(tool_name, tool_input)

        decision = Decision.ALLOW
        reason = ""
        alert_records: list[tuple[Alert, Decision, str]] = []
        pathless_denies: list[tuple[Decision, str, str | None]] = []

        for step in steps:
            alerts = check_step(step, 0, cwd=cwd)
            verdict = active_engine.evaluate(
                PolicyContext(
                    agent=AGENT,
                    session_id=session_id,
                    cwd=cwd,
                    step=step,
                    step_index=0,
                    alerts=alerts,
                )
            )
            if _RANK[verdict.decision] > _RANK[decision]:
                decision, reason = verdict.decision, verdict.reason
            for a in alerts:
                alert_records.append((a, verdict.decision, verdict.reason))
            if not alerts and verdict.decision is not Decision.ALLOW:
                from agentbench.core.steps import step_path
                pathless_denies.append(
                    (verdict.decision, verdict.reason, step_path(step.get("args") or {}))
                )

        if record:
            _record(
                session_id=session_id,
                cwd=cwd,
                audit_db=audit_db,
                alert_records=alert_records,
                pathless_denies=pathless_denies,
            )

        return HookResult(0, _permission_output(decision, reason))
    except Exception as exc:  # absolute backstop
        # Honor the config's fail mode: fail open (allow) by default, or fail
        # closed (deny) if the user asked for it. Never crash the agent.
        if on_error == "deny":
            print(f"[agentbench] hook error (denying, fail-closed): {exc}", file=sys.stderr)
            return HookResult(0, _permission_output(
                Decision.DENY, "AgentBench policy error — denied (fail-closed)."))
        print(f"[agentbench] hook error (allowing): {exc}", file=sys.stderr)
        return HookResult(0, "")


def _record(
    *,
    session_id: str,
    cwd: str | None,
    audit_db: Path | str | None,
    alert_records: list[tuple[Alert, Decision, str]],
    pathless_denies: list[tuple[Decision, str, str | None]],
) -> None:
    """Append enforcement decisions to the hash-chained audit trail.

    Only records things worth recording: any alerting step, and any
    deny/ask with no underlying alert (a protected-path block). Benign
    allows write nothing -- same discipline as the watch loop.
    """
    if not alert_records and not pathless_denies:
        return
    from agentbench.accountability.audit import AuditStore, record_from_verdict

    try:
        store = AuditStore(audit_db)
    except Exception as exc:
        print(f"[agentbench] could not open audit trail: {exc}", file=sys.stderr)
        return
    try:
        base = store.session_event_count(session_id)
        idx = base
        for alert, decision, reason in alert_records:
            rec = record_from_verdict(
                agent=AGENT, session_id=session_id, cwd=cwd, model=None,
                step_index=idx, decision=decision, reason=reason,
                rule=alert.rule, severity=alert.severity,
                title=alert.title, detail=alert.detail, path=alert.path,
            )
            _safe_append(store, rec)
            idx += 1
        for decision, reason, path in pathless_denies:
            rec = record_from_verdict(
                agent=AGENT, session_id=session_id, cwd=cwd, model=None,
                step_index=idx, decision=decision, reason=reason,
                rule="protected_path", path=path,
            )
            _safe_append(store, rec)
            idx += 1
    finally:
        store.close()


def _safe_append(store: Any, record: dict[str, Any]) -> None:
    try:
        store.append(record)
    except Exception as exc:  # a write failure must not block the tool call
        print(f"[agentbench] failed to record enforcement decision: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: read stdin, evaluate, write decision to stdout."""
    stdin_text = sys.stdin.read()
    result = run_hook(stdin_text)
    if result.stdout:
        sys.stdout.write(result.stdout)
    return result.exit_code
