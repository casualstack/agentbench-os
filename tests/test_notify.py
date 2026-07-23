"""Tests for optional, best-effort desktop notifications.

Runs headless with no notification dependency installed and no display, so
every function must run without raising and without popping a real
notification — backends are mocked out wherever they'd actually fire.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agentbench.accountability.notify import backend_available, notify, summarize_alerts


@dataclass
class _Alert:
    rule: str
    severity: str
    title: str
    detail: str
    step_index: int = 0
    path: str | None = None


@dataclass
class _Event:
    agent: str = "claude-code"
    session_id: str = "abcd1234"
    cwd: str | None = "C:\\work\\myrepo"
    alerts: list = field(default_factory=list)


def test_module_imports_cleanly():
    import agentbench.accountability.notify  # noqa: F401


def test_notify_returns_false_with_no_backend(monkeypatch):
    monkeypatch.setattr("agentbench.accountability.notify._notify_plyer", lambda t, m: False)
    monkeypatch.setattr("agentbench.accountability.notify._notify_shell", lambda t, m: False)
    assert notify("title", "message") is False


def test_notify_swallows_backend_exceptions(monkeypatch):
    def _boom(title, message):
        raise RuntimeError("no display available")

    monkeypatch.setattr("agentbench.accountability.notify._notify_plyer", _boom)
    monkeypatch.setattr("agentbench.accountability.notify._notify_shell", _boom)
    assert notify("title", "message") is False


def test_notify_returns_true_when_a_backend_delivers(monkeypatch):
    monkeypatch.setattr("agentbench.accountability.notify._notify_plyer", lambda t, m: False)
    monkeypatch.setattr("agentbench.accountability.notify._notify_shell", lambda t, m: True)
    assert notify("title", "message") is True


def test_backend_available_never_raises(monkeypatch):
    monkeypatch.setattr(
        "agentbench.accountability.notify.platform.system",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert backend_available() is False


def test_backend_available_returns_bool():
    assert backend_available() in (True, False)


def test_notify_shell_dispatches_by_platform_without_raising(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr("agentbench.accountability.notify.subprocess.run", fake_run)
    monkeypatch.setattr("agentbench.accountability.notify.shutil.which", lambda name: "/usr/bin/" + name)

    for system in ("Darwin", "Linux", "Windows", "SomeOtherOS"):
        monkeypatch.setattr("agentbench.accountability.notify.platform.system", lambda system=system: system)
        from agentbench.accountability.notify import _notify_shell

        result = _notify_shell("title", "message")
        assert result in (True, False)


def test_summarize_alerts_empty_is_none():
    assert summarize_alerts([]) is None
    assert summarize_alerts([_Event(alerts=[])]) is None


def test_summarize_alerts_batches_into_one_notification():
    alerts = [
        _Alert("destructive_command", "critical", "Ran a destructive command", "..."),
        _Alert("network_command", "warning", "Reached out to the network", "..."),
    ]
    summary = summarize_alerts([_Event(alerts=alerts)])
    assert summary is not None
    title, message = summary
    assert "2" in title
    assert "myrepo" in title
    assert "Ran a destructive command" in message
    assert "Reached out to the network" in message


def test_summarize_alerts_counts_critical_and_multiple_projects():
    critical_alert = _Alert("destructive_command", "critical", "Ran a destructive command", "...")
    warning_alert = _Alert("network_command", "warning", "Reached out to the network", "...")
    event1 = _Event(cwd="C:\\work\\repo-a", alerts=[critical_alert])
    event2 = _Event(cwd="C:\\work\\repo-b", alerts=[warning_alert])

    title, message = summarize_alerts([event1, event2])
    assert "2" in title
    assert "1 critical" in title
    assert "2 projects" in title


def test_summarize_alerts_truncates_long_lists():
    alerts = [
        _Alert("network_command", "warning", f"Alert number {i}", "...") for i in range(8)
    ]
    title, message = summarize_alerts([_Event(alerts=alerts)])
    assert "8" in title
    assert "more" in message
