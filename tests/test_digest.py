"""Tests for the plain-English markdown session digest."""

from __future__ import annotations

from agentbench.watch.digest import render_digest


def _alert(rule, severity, title, detail, step_index=0, path=None):
    return {
        "rule": rule,
        "severity": severity,
        "title": title,
        "detail": detail,
        "step_index": step_index,
        "path": path,
    }


def _session(session_id, alerts, *, cwd="C:\\work\\myrepo", steps=3):
    return {
        "agent": "claude-code",
        "session_id": session_id,
        "path": f"C:\\.claude\\projects\\{session_id}.jsonl",
        "cwd": cwd,
        "model": "claude-sonnet-5",
        "steps": steps,
        "alerts": alerts,
    }


def test_no_sessions_reports_no_issues():
    assert render_digest([]) == "No issues found.\n"


def test_session_with_no_alerts_is_clean():
    sessions = [_session("s1abcdef", [])]
    out = render_digest(sessions)
    assert "1 session watched. No issues found." in out
    assert "No issues found in this session." in out
    assert "claude-sonnet-5" in out


def test_critical_alerts_render_before_warnings():
    sessions = [
        _session(
            "s1abcdef",
            [
                _alert("network_command", "warning", "Reached out to the network", "warn detail"),
                _alert("destructive_command", "critical", "Ran a destructive command", "crit detail"),
            ],
        )
    ]
    out = render_digest(sessions)
    assert out.index("Ran a destructive command") < out.index("Reached out to the network")
    assert "### Critical" in out
    assert "### Warnings" in out
    assert "1 session watched, 2 issues found (1 critical)." in out


def test_multiple_sessions_are_grouped_separately():
    sessions = [
        _session(
            "s1abcdef",
            [_alert("destructive_command", "critical", "Ran a destructive command", "crit detail")],
            cwd="C:\\work\\repo-a",
        ),
        _session("s2ghijkl", [], cwd="C:\\work\\repo-b"),
    ]
    out = render_digest(sessions)
    assert "2 sessions watched, 1 issue found (1 critical)." in out
    assert "s1abcdef" in out
    assert "s2ghijkl" in out
    assert "No issues found in this session." in out


def test_client_label_is_derived_from_adapters_registry():
    # digest.py derives display labels from agentbench.adapters.ADAPTERS
    # rather than hardcoding them, so newly-parsed clients (like Codex) label
    # correctly without a digest.py change.
    session = _session("s1abcdef", [])
    session["agent"] = "codex"
    out = render_digest([session])
    assert "## Codex CLI session" in out


def test_unknown_agent_falls_back_to_raw_name():
    session = _session("s1abcdef", [])
    session["agent"] = "some-future-client"
    out = render_digest([session])
    assert "## some-future-client session" in out


def test_output_is_written_for_a_non_expert():
    sessions = [
        _session(
            "s1abcdef",
            [_alert("deleted_assertion", "critical", "Deleted a test assertion", "The agent removed a check.")],
        )
    ]
    out = render_digest(sessions)
    assert "trajectory" not in out.lower()
    assert "Deleted a test assertion" in out
    assert "The agent removed a check." in out
