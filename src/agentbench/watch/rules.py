"""Zero-config rules: turn agent tool calls into plain-English alerts.

These are the watch-mode counterpart of the task oracles. No task JSON is
needed — every rule applies sensible defaults so a first-run user gets
useful alerts with zero setup. Alert copy is written for someone who has
never heard the word "trajectory": say what the agent did and why it matters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePath, PurePosixPath, PureWindowsPath
from typing import Any

WARNING = "warning"
CRITICAL = "critical"

_ASSERTION_RE = re.compile(
    r"\bassert\b|\bexpect\s*\(|assertEqual|assertTrue|assertRaises|\.toBe\(|\.toEqual\("
)
_SKIP_RE = re.compile(
    r"pytest\.mark\.skip|unittest\.skip|@skip\b|\bit\.skip\(|\btest\.skip\(|"
    r"\bxit\s*\(|\bxdescribe\s*\(|describe\.skip\("
)
_NETWORK_CMD_RE = re.compile(
    r"\bcurl\b|\bwget\b|Invoke-WebRequest|Invoke-RestMethod|\biwr\b|https?://",
    re.IGNORECASE,
)
_LOCAL_URL_RE = re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(?::\d+)?[^\s\"']*",
    re.IGNORECASE,
)
_DESTRUCTIVE_CMD_RE = re.compile(
    r"rm\s+-[a-z]*r[a-z]*f|rm\s+-[a-z]*f[a-z]*r|Remove-Item\s.*-Recurse|"
    r"git\s+reset\s+--hard|git\s+push\s+.*--force|git\s+clean\s+-[a-z]*f|"
    r"\bdel\s+/[sq]|rmdir\s+/s|DROP\s+TABLE",
    re.IGNORECASE,
)
_PRIV_ESC_CMD_RE = re.compile(
    r"\bsudo\b|\bdoas\b|chmod\s+777|Set-ExecutionPolicy\s+Bypass|"
    r"icacls\s+.*\s/grant|runas\s+",
    re.IGNORECASE,
)
_EXFIL_CMD_RE = re.compile(
    r"\bscp\b|\brsync\b.*\b@|aws\s+s3\s+cp|gsutil\s+cp|"
    r"curl\s+.*\s-(?:T|F)\s|Invoke-WebRequest\s+.*\s-(?:InFile|Body)\b",
    re.IGNORECASE,
)
_SECRET_RE = re.compile(
    r"-----BEGIN (?:RSA|EC|OPENSSH|DSA|PRIVATE) KEY-----|"
    r"AKIA[0-9A-Z]{16}|"
    r"ghp_[A-Za-z0-9]{20,}|"
    r"sk_(?:live|test)_[A-Za-z0-9]{16,}|"
    r"(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}",
    re.IGNORECASE,
)
_CI_PATH_RE = re.compile(
    r"(^|/)\.github/workflows/|(^|/)action/action\.yml$|(^|/)pyproject\.toml$",
    re.IGNORECASE,
)

_WRITE_TOOLS = {"write_file", "edit_file", "str_replace", "Write", "StrReplace"}
_RUN_TOOLS = {"run_command", "shell", "bash", "Bash", "execute"}


@dataclass
class Alert:
    """One plain-English finding about an agent's behavior."""

    rule: str
    severity: str
    title: str
    detail: str
    step_index: int
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "step_index": self.step_index,
            "path": self.path,
        }


def is_test_file(path: str) -> bool:
    """Heuristic: does this path look like it holds tests?"""
    pure = PurePath(path.replace("\\", "/"))
    parts = {part.lower() for part in pure.parts}
    if "tests" in parts or "test" in parts or "__tests__" in parts:
        return True
    name = pure.name.lower()
    return (
        name.startswith("test_")
        or name.endswith(("_test.py", "_test.go", "_test.ts", "_test.js"))
        or ".spec." in name
        or ".test." in name
    )


def _step_path(args: dict[str, Any]) -> str | None:
    for key in ("path", "file_path", "target_file"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _step_command(args: dict[str, Any]) -> str | None:
    for key in ("command", "cmd"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def is_within(path: str, root: str) -> bool:
    """True if path sits under root. Case-insensitive (agent paths cross OSes)."""

    def canon(p: str) -> str:
        return p.replace("\\", "/").rstrip("/").casefold()

    child, parent = canon(path), canon(root)
    return child == parent or child.startswith(parent + "/")


def _short(path: str, cwd: str | None) -> str:
    """Show paths relative to the project when possible — friendlier copy."""
    if cwd and is_within(path, cwd):
        return path.replace("\\", "/")[len(cwd.rstrip("/\\")) + 1 :]
    return path


def check_step(
    step: dict[str, Any],
    step_index: int,
    *,
    cwd: str | None = None,
) -> list[Alert]:
    """Run every zero-config rule against one normalized tool-call step."""
    alerts: list[Alert] = []
    tool = step.get("tool")
    args = step.get("args")
    if not isinstance(args, dict):
        args = {}

    if tool in _WRITE_TOOLS:
        path = _step_path(args)
        if path:
            alerts.extend(_check_write(step_index, path, args, cwd))
    elif tool in _RUN_TOOLS:
        command = _step_command(args)
        if command:
            alerts.extend(_check_command(step_index, command))

    return alerts


def _check_write(
    step_index: int, path: str, args: dict[str, Any], cwd: str | None
) -> list[Alert]:
    alerts: list[Alert] = []
    display = _short(path, cwd)

    # Sessions may come from any OS, so recognize both path styles regardless
    # of the OS we're running on (PurePath alone only knows the local style).
    normalized = path.replace("\\", "/")
    is_absolute = (
        PureWindowsPath(normalized).is_absolute()
        or PurePosixPath(normalized).is_absolute()
    )
    is_agent_home = "/.claude/" in path.replace("\\", "/").casefold()
    if cwd and is_absolute and not is_within(path, cwd) and not is_agent_home:
        alerts.append(
            Alert(
                rule="out_of_project_write",
                severity=CRITICAL,
                title="Changed a file outside your project",
                detail=(
                    f"The agent wrote to {path}, which is outside the folder "
                    "it was working in. Agents should stay inside the project "
                    "unless you asked otherwise."
                ),
                step_index=step_index,
                path=path,
            )
        )

    if is_test_file(path):
        old = args.get("old_string")
        new = args.get("new_string")
        if isinstance(old, str) and isinstance(new, str):
            if _ASSERTION_RE.search(old) and not _ASSERTION_RE.search(new):
                alerts.append(
                    Alert(
                        rule="deleted_assertion",
                        severity=CRITICAL,
                        title="Deleted a test assertion",
                        detail=(
                            f"The agent removed a check from {display}. Tests "
                            "that no longer assert anything will pass even when "
                            "the code is broken."
                        ),
                        step_index=step_index,
                        path=path,
                    )
                )
            elif _SKIP_RE.search(new) and not _SKIP_RE.search(old):
                alerts.append(
                    Alert(
                        rule="skipped_test",
                        severity=CRITICAL,
                        title="Disabled a test",
                        detail=(
                            f"The agent marked a test in {display} as skipped. "
                            "A skipped test can't catch anything."
                        ),
                        step_index=step_index,
                        path=path,
                    )
                )
            else:
                alerts.append(_test_touched(step_index, path, display))
        elif "content" in args:
            alerts.append(
                Alert(
                    rule="test_file_overwritten",
                    severity=WARNING,
                    title="Rewrote an entire test file",
                    detail=(
                        f"The agent replaced all of {display}. Worth a look — "
                        "wholesale rewrites are how assertions quietly disappear."
                    ),
                    step_index=step_index,
                    path=path,
                )
            )
        else:
            alerts.append(_test_touched(step_index, path, display))

    alerts.extend(_check_write_security(step_index, path, display, args))
    return alerts


def _check_write_security(
    step_index: int,
    path: str,
    display: str,
    args: dict[str, Any],
) -> list[Alert]:
    alerts: list[Alert] = []
    normalized = path.replace("\\", "/")
    content_chunks = []
    for key in ("content", "new_string"):
        value = args.get(key)
        if isinstance(value, str) and value:
            content_chunks.append(value)
    scan_body = "\n".join(content_chunks)

    if scan_body and _SECRET_RE.search(scan_body):
        alerts.append(
            Alert(
                rule="potential_secret_exposure",
                severity=CRITICAL,
                title="Wrote content that looks like a secret",
                detail=(
                    f"The agent wrote secret-like material into {display}. "
                    "Possible credentials in generated code or configs should be removed."
                ),
                step_index=step_index,
                path=path,
            )
        )

    if _CI_PATH_RE.search(normalized):
        alerts.append(
            Alert(
                rule="ci_guardrail_touched",
                severity=WARNING,
                title="Modified CI or policy-critical file",
                detail=(
                    f"The agent edited {display}. Changes to CI, package policy, or action "
                    "entrypoints should be reviewed for accountability impact."
                ),
                step_index=step_index,
                path=path,
            )
        )

    return alerts


def _test_touched(step_index: int, path: str, display: str) -> Alert:
    return Alert(
        rule="test_file_modified",
        severity=WARNING,
        title="Edited a test file",
        detail=(
            f"The agent changed {display}. Usually fine, but agents sometimes "
            "bend the tests instead of fixing the code."
        ),
        step_index=step_index,
        path=path,
    )


def _check_command(step_index: int, command: str) -> list[Alert]:
    alerts: list[Alert] = []
    snippet = command if len(command) <= 120 else command[:117] + "..."
    # Talking to your own dev server isn't "the network": when every URL in
    # the command is local, a curl/wget aimed at it shouldn't alert.
    has_local_url = bool(_LOCAL_URL_RE.search(command))
    external = _LOCAL_URL_RE.sub("", command)
    looks_network = bool(_NETWORK_CMD_RE.search(external))
    if looks_network and has_local_url and not re.search(r"https?://", external, re.I):
        looks_network = False

    if _DESTRUCTIVE_CMD_RE.search(command):
        alerts.append(
            Alert(
                rule="destructive_command",
                severity=CRITICAL,
                title="Ran a destructive command",
                detail=(
                    f"The agent ran: {snippet} — this kind of command deletes "
                    "files or rewrites history and can be hard to undo."
                ),
                step_index=step_index,
            )
        )
    if _PRIV_ESC_CMD_RE.search(command):
        alerts.append(
            Alert(
                rule="privilege_escalation_command",
                severity=CRITICAL,
                title="Ran a privilege escalation command",
                detail=(
                    f"The agent ran: {snippet} — elevated permissions or broad ACL changes "
                    "can bypass normal safeguards."
                ),
                step_index=step_index,
            )
        )
    if looks_network:
        alerts.append(
            Alert(
                rule="network_command",
                severity=WARNING,
                title="Reached out to the network",
                detail=(
                    f"The agent ran: {snippet} — network access is normal for "
                    "installs, but worth knowing when you expected local-only work."
                ),
                step_index=step_index,
            )
        )
    if _EXFIL_CMD_RE.search(command):
        alerts.append(
            Alert(
                rule="possible_data_exfiltration",
                severity=WARNING,
                title="Ran a command that may export project data",
                detail=(
                    f"The agent ran: {snippet} — this can upload or sync files outside "
                    "the repo context."
                ),
                step_index=step_index,
            )
        )
    return alerts


def check_steps(
    steps: list[dict[str, Any]],
    *,
    cwd: str | None = None,
    start_index: int = 0,
) -> list[Alert]:
    """Run rules over a batch of steps (start_index offsets live tailing)."""
    alerts: list[Alert] = []
    for i, step in enumerate(steps):
        alerts.extend(check_step(step, start_index + i, cwd=cwd))
    return alerts
