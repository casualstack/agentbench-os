"""Tests for the Codex CLI adapter: real rollout JSONL parsing."""

from __future__ import annotations

import json
from pathlib import Path

from agentbench.watch.adapters.codex import CodexAdapter
from agentbench.watch.rules import check_steps
from agentbench.watch.sources import discover_sessions
from agentbench.watch.watcher import SessionWatcher

CWD = "C:\\work\\myrepo"
SESSION_ID = "019f26ba-315b-7480-92d2-e7b346207df4"


def _session_meta_line(session_id: str = SESSION_ID, cwd: str = CWD) -> str:
    return json.dumps(
        {
            "timestamp": "2026-07-03T06:46:47.742Z",
            "type": "session_meta",
            "payload": {
                "session_id": session_id,
                "id": session_id,
                "cwd": cwd,
                "cli_version": "0.142.5",
            },
        }
    )


def _turn_context_line(cwd: str = CWD, model: str = "gpt-5.5") -> str:
    return json.dumps(
        {
            "timestamp": "2026-07-03T06:46:47.771Z",
            "type": "turn_context",
            "payload": {"turn_id": "t1", "cwd": cwd, "model": model},
        }
    )


def _shell_command_line(command: str, workdir: str = CWD) -> str:
    return json.dumps(
        {
            "timestamp": "2026-07-03T06:46:57.420Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell_command",
                "arguments": json.dumps({"command": command, "workdir": workdir}),
                "call_id": "call_1",
            },
        }
    )


def _apply_patch_line(patch: str) -> str:
    return json.dumps(
        {
            "timestamp": "2026-07-03T06:52:25.598Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "status": "completed",
                "call_id": "call_2",
                "name": "apply_patch",
                "input": patch,
            },
        }
    )


def _write_rollout(root: Path, filename: str, lines: list[str]) -> Path:
    day_dir = root / ".codex" / "sessions" / "2026" / "07" / "03"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / filename
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


_ROLLOUT_FILENAME = f"rollout-2026-07-03T02-46-04-{SESSION_ID}.jsonl"

_DELETE_ASSERTION_PATCH = (
    "*** Begin Patch\n"
    "*** Update File: tests/test_app.py\n"
    "@@\n"
    "-assert add(1, 2) == 3\n"
    "+pass\n"
    "*** End Patch\n"
)


class TestDiscovery:
    def test_detect_requires_sessions_dir(self, tmp_path):
        adapter = CodexAdapter()
        assert not adapter.detect(tmp_path)
        (tmp_path / ".codex").mkdir()
        assert not adapter.detect(tmp_path)  # ".codex" alone isn't enough
        (tmp_path / ".codex" / "sessions").mkdir()
        assert adapter.detect(tmp_path)

    def test_discover_finds_nested_rollout_files(self, tmp_path):
        _write_rollout(tmp_path, _ROLLOUT_FILENAME, [_session_meta_line()])
        adapter = CodexAdapter()
        sources = adapter.discover(tmp_path)
        assert len(sources) == 1
        assert sources[0].agent == "codex"
        assert sources[0].session_id == SESSION_ID  # pulled from the filename

    def test_discovery_flows_through_registry(self, tmp_path):
        _write_rollout(tmp_path, _ROLLOUT_FILENAME, [_session_meta_line()])
        report = discover_sessions(home=tmp_path)
        assert "codex" in report.detected_agents
        codex_sessions = [s for s in report.sessions if s.agent == "codex"]
        assert len(codex_sessions) == 1


class TestParsing:
    def test_extracts_metadata_and_normalized_steps(self, tmp_path):
        path = _write_rollout(
            tmp_path,
            _ROLLOUT_FILENAME,
            [
                _session_meta_line(),
                _turn_context_line(),
                _shell_command_line("pytest -q"),
                _apply_patch_line(_DELETE_ASSERTION_PATCH),
            ],
        )
        doc = CodexAdapter().parse_session(path)

        assert doc["metadata"]["agent"] == "codex"
        assert doc["metadata"]["cwd"] == CWD
        assert doc["metadata"]["model"] == "gpt-5.5"
        assert doc["metadata"]["session_id"] == SESSION_ID
        assert doc["metadata"]["cli_version"] == "0.142.5"

        assert [s["tool"] for s in doc["steps"]] == ["run_command", "str_replace"]
        assert doc["steps"][0]["args"]["command"] == "pytest -q"
        assert doc["steps"][0]["agent_tool"] == "shell_command"
        assert doc["steps"][1]["args"]["file_path"] == "tests/test_app.py"
        assert doc["steps"][1]["args"]["old_string"] == "assert add(1, 2) == 3"
        assert doc["steps"][1]["args"]["new_string"] == "pass"

    def test_shell_command_array_form_is_joined(self, tmp_path):
        line = json.dumps(
            {
                "timestamp": "t",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "shell_command",
                    "arguments": json.dumps({"command": ["git", "status", "--short"]}),
                },
            }
        )
        path = _write_rollout(tmp_path, _ROLLOUT_FILENAME, [line])
        doc = CodexAdapter().parse_session(path)
        assert doc["steps"][0]["args"]["command"] == "git status --short"

    def test_add_file_patch_becomes_write_file(self, tmp_path):
        patch = (
            "*** Begin Patch\n"
            "*** Add File: src/new_module.py\n"
            "+def add(a, b):\n"
            "+    return a + b\n"
            "*** End Patch\n"
        )
        path = _write_rollout(tmp_path, _ROLLOUT_FILENAME, [_apply_patch_line(patch)])
        doc = CodexAdapter().parse_session(path)
        assert doc["steps"] == [
            {
                "type": "tool_call",
                "tool": "write_file",
                "args": {
                    "file_path": "src/new_module.py",
                    "content": "def add(a, b):\n    return a + b",
                },
                "agent_tool": "apply_patch",
            }
        ]

    def test_delete_then_add_same_path_is_one_write_step(self, tmp_path):
        patch = (
            "*** Begin Patch\n"
            "*** Delete File: index.html\n"
            "*** Add File: index.html\n"
            "+<html></html>\n"
            "*** End Patch\n"
        )
        path = _write_rollout(tmp_path, _ROLLOUT_FILENAME, [_apply_patch_line(patch)])
        doc = CodexAdapter().parse_session(path)
        assert len(doc["steps"]) == 1
        assert doc["steps"][0]["tool"] == "write_file"
        assert doc["steps"][0]["args"]["file_path"] == "index.html"
        assert doc["steps"][0]["args"]["content"] == "<html></html>"

    def test_delete_only_patch_emits_empty_write(self, tmp_path):
        patch = "*** Begin Patch\n*** Delete File: old.py\n*** End Patch\n"
        path = _write_rollout(tmp_path, _ROLLOUT_FILENAME, [_apply_patch_line(patch)])
        doc = CodexAdapter().parse_session(path)
        assert doc["steps"] == [
            {
                "type": "tool_call",
                "tool": "write_file",
                "args": {"file_path": "old.py", "content": ""},
                "agent_tool": "apply_patch",
            }
        ]

    def test_unknown_function_call_is_skipped(self, tmp_path):
        line = json.dumps(
            {
                "timestamp": "t",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "js", "arguments": "{}"},
            }
        )
        path = _write_rollout(tmp_path, _ROLLOUT_FILENAME, [line])
        assert CodexAdapter().parse_session(path)["steps"] == []

    def test_malformed_lines_never_crash_parsing(self, tmp_path):
        path = _write_rollout(
            tmp_path,
            _ROLLOUT_FILENAME,
            [_session_meta_line(), "", "{not json", "null", '"a string"'],
        )
        doc = CodexAdapter().parse_session(path)
        assert doc["steps"] == []
        assert doc["metadata"]["agent"] == "codex"

    def test_parse_session_degrades_on_missing_file(self, tmp_path):
        doc = CodexAdapter().parse_session(tmp_path / "nope" / "rollout-x.jsonl")
        assert doc["steps"] == []
        assert doc["metadata"]["agent"] == "codex"


class TestRulesFlow:
    def test_deleted_assertion_alert_fires_on_apply_patch(self, tmp_path):
        path = _write_rollout(
            tmp_path,
            _ROLLOUT_FILENAME,
            [
                _session_meta_line(),
                _turn_context_line(),
                _apply_patch_line(_DELETE_ASSERTION_PATCH),
            ],
        )
        doc = CodexAdapter().parse_session(path)
        alerts = check_steps(doc["steps"], cwd=doc["metadata"]["cwd"])
        assert [a.rule for a in alerts] == ["deleted_assertion"]
        assert alerts[0].severity == "critical"

    def test_weakened_assertion_alert_fires_on_apply_patch(self, tmp_path):
        patch = (
            "*** Begin Patch\n"
            "*** Update File: tests/test_app.py\n"
            "@@\n"
            "-assert add(1, 2) == 3\n"
            "+assert True\n"
            "*** End Patch\n"
        )
        path = _write_rollout(
            tmp_path, _ROLLOUT_FILENAME, [_session_meta_line(), _apply_patch_line(patch)]
        )
        doc = CodexAdapter().parse_session(path)
        alerts = check_steps(doc["steps"], cwd=doc["metadata"]["cwd"])
        assert [a.rule for a in alerts] == ["weakened_assertion"]

    def test_destructive_shell_command_alert_fires(self, tmp_path):
        path = _write_rollout(
            tmp_path,
            _ROLLOUT_FILENAME,
            [_session_meta_line(), _shell_command_line("rm -rf build/")],
        )
        doc = CodexAdapter().parse_session(path)
        alerts = check_steps(doc["steps"], cwd=doc["metadata"]["cwd"])
        assert [a.rule for a in alerts] == ["destructive_command"]

    def test_watcher_tails_a_codex_session_end_to_end(self, tmp_path):
        _write_rollout(
            tmp_path,
            _ROLLOUT_FILENAME,
            [
                _session_meta_line(),
                _turn_context_line(),
                _apply_patch_line(_DELETE_ASSERTION_PATCH),
            ],
        )
        watcher = SessionWatcher(home=tmp_path)
        events = watcher.poll()

        codex_events = [e for e in events if e.agent == "codex"]
        assert len(codex_events) == 1
        assert codex_events[0].cwd == CWD
        assert codex_events[0].model == "gpt-5.5"
        assert [a.rule for a in codex_events[0].alerts] == ["deleted_assertion"]

        sessions = watcher.sessions()
        codex_sessions = [s for s in sessions if s["agent"] == "codex"]
        assert codex_sessions[0]["client"] == "Codex CLI"

        # Nothing new on the next poll.
        assert watcher.poll() == []
