"""Render a SessionWatcher.sessions() snapshot as a plain-English markdown digest.

Meant to be shared with someone who has never heard the word "trajectory":
plain language, critical issues first, nothing to configure.
"""

from __future__ import annotations

from typing import Any

from agentbench.adapters import ADAPTERS

_SEVERITY_ORDER = ("critical", "warning")
_SEVERITY_LABEL = {"critical": "Critical", "warning": "Warnings"}
_AGENT_LABEL = {a.client_name: a.display_name for a in ADAPTERS}


def render_digest(sessions: list[dict[str, Any]]) -> str:
    """Render a watcher snapshot as shareable markdown."""
    if not sessions:
        return "No issues found.\n"

    all_alerts = [alert for session in sessions for alert in session.get("alerts", [])]
    critical = sum(1 for alert in all_alerts if alert.get("severity") == "critical")

    lines = ["# AgentBench Session Digest", "", _summary_line(len(sessions), len(all_alerts), critical), ""]
    for session in sessions:
        lines.extend(_render_session(session))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _summary_line(session_count: int, issue_count: int, critical_count: int) -> str:
    session_word = "session" if session_count == 1 else "sessions"
    if issue_count == 0:
        return f"**{session_count} {session_word} watched. No issues found.**"
    issue_word = "issue" if issue_count == 1 else "issues"
    detail = f" ({critical_count} critical)" if critical_count else ""
    return f"**{session_count} {session_word} watched, {issue_count} {issue_word} found{detail}.**"


def _render_session(session: dict[str, Any]) -> list[str]:
    agent = _AGENT_LABEL.get(session.get("agent"), session.get("agent") or "Unknown agent")
    session_id = str(session.get("session_id") or "")[:8]
    where = session.get("cwd") or session.get("path") or "unknown location"

    lines = [f"## {agent} session {session_id} — {where}"]
    model = session.get("model")
    if model:
        lines.append(f"- Model: {model}")
    lines.append(f"- Steps: {session.get('steps', 0)}")
    lines.append("")

    alerts = session.get("alerts") or []
    if not alerts:
        lines.append("No issues found in this session.")
        return lines

    by_severity: dict[str, list[dict[str, Any]]] = {}
    for alert in alerts:
        by_severity.setdefault(alert.get("severity", "warning"), []).append(alert)

    for severity in _SEVERITY_ORDER:
        group = by_severity.get(severity)
        if not group:
            continue
        lines.append(f"### {_SEVERITY_LABEL[severity]}")
        for alert in group:
            lines.append(f"- **{alert.get('title')}** — {alert.get('detail')}")
        lines.append("")

    return lines
