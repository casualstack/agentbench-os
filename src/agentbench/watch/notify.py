"""Best-effort desktop notifications for watch mode.

Zero-config and local-only: notifications never leave the machine, and this
module never raises — a broken or missing backend just means no popup, not a
crashed CLI. An optional library is tried first (see the ``notify`` extra in
pyproject.toml); everything still works without it via OS shell fallbacks.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any

_MAX_LINES = 5


def notify(title: str, message: str) -> bool:
    """Show one desktop notification. Returns whether it was actually delivered.

    Tries each backend in order and swallows any exception — a notification
    failure must never take down ``agentbench watch``.
    """
    for backend in (_notify_plyer, _notify_shell):
        try:
            if backend(title, message):
                return True
        except Exception:
            continue
    return False


def backend_available() -> bool:
    """Best-effort check for whether *some* backend could deliver a notification.

    Used to pick a sane default for --notify without actually popping one.
    """
    try:
        if _has_plyer():
            return True
        system = platform.system()
        if system == "Darwin":
            return shutil.which("osascript") is not None
        if system == "Linux":
            return shutil.which("notify-send") is not None
        if system == "Windows":
            return shutil.which("powershell") is not None or shutil.which("pwsh") is not None
        return False
    except Exception:
        return False


def summarize_alerts(events: list[Any]) -> tuple[str, str] | None:
    """Condense one poll's new alerts into a single title/message pair.

    Batching matters: a project's whole history can surface dozens of alerts
    on the first poll, and that should be one notification, not a burst.
    Returns None when there is nothing to report.
    """
    items: list[tuple[Any, Any]] = [
        (alert, event) for event in events for alert in event.alerts
    ]
    if not items:
        return None

    total = len(items)
    critical = sum(1 for alert, _ in items if alert.severity == "critical")
    projects = {_project_name(event.cwd) for _, event in items}
    where = projects.pop() if len(projects) == 1 else f"{len(projects)} projects"

    issue_word = "issue" if total == 1 else "issues"
    title = f"AgentBench: {total} {issue_word} in {where}"
    if critical:
        title += f" ({critical} critical)"

    lines = [f"- {alert.title}" for alert, _ in items[:_MAX_LINES]]
    if total > _MAX_LINES:
        lines.append(f"...and {total - _MAX_LINES} more")
    message = "\n".join(lines)

    return title, message


def _project_name(cwd: str | None) -> str:
    if not cwd:
        return "an unwatched project"
    normalized = cwd.replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] or normalized


def _has_plyer() -> bool:
    try:
        import plyer  # noqa: F401

        return True
    except ImportError:
        return False


def _notify_plyer(title: str, message: str) -> bool:
    try:
        from plyer import notification
    except ImportError:
        return False
    notification.notify(title=title, message=message, timeout=8)
    return True


def _notify_shell(title: str, message: str) -> bool:
    system = platform.system()
    if system == "Darwin":
        return _notify_macos(title, message)
    if system == "Linux":
        return _notify_linux(title, message)
    if system == "Windows":
        return _notify_windows(title, message)
    return False


def _notify_macos(title: str, message: str) -> bool:
    script = (
        f'display notification "{_escape_applescript(message)}" '
        f'with title "{_escape_applescript(title)}"'
    )
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, timeout=5
    )
    return result.returncode == 0


def _notify_linux(title: str, message: str) -> bool:
    if shutil.which("notify-send") is None:
        return False
    result = subprocess.run(
        ["notify-send", title, message], capture_output=True, timeout=5
    )
    return result.returncode == 0


def _notify_windows(title: str, message: str) -> bool:
    if shutil.which("powershell") is None and shutil.which("pwsh") is None:
        return False
    exe = "powershell" if shutil.which("powershell") else "pwsh"
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$n = New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon = [System.Drawing.SystemIcons]::Information;"
        "$n.Visible = $true;"
        f"$n.ShowBalloonTip(8000, {_escape_powershell(title)}, "
        f"{_escape_powershell(message)}, "
        "[System.Windows.Forms.ToolTipIcon]::Info);"
        "Start-Sleep -Seconds 1;"
        "$n.Dispose()"
    )
    result = subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        timeout=10,
    )
    return result.returncode == 0


def _escape_applescript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _escape_powershell(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"
