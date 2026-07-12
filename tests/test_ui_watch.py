"""Tests for the live-watch endpoints on the dashboard server."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from agentbench.ui.server import make_server

REPO_ROOT = Path(__file__).parent.parent
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


def _get(url: str) -> dict:
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


@pytest.fixture
def watch_server(tmp_path):
    _write_session(
        tmp_path,
        "s1",
        [
            _session_line("Write", {"file_path": "src/app.py", "content": "x"}),
            _session_line(
                "Edit",
                {
                    "file_path": "tests/test_app.py",
                    "old_string": "assert app() == 1",
                    "new_string": "pass",
                },
            ),
        ],
    )
    server = make_server(REPO_ROOT, tasks_dir="tasks", port=0, watch_home=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    server.shutdown()
    server.server_close()


def test_index_serves_live_watch_view():
    server = make_server(REPO_ROOT, tasks_dir="tasks", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(base + "/") as response:
            body = response.read().decode("utf-8")
        assert 'data-tab="watch"' in body
        assert 'id="tab-watch"' in body
    finally:
        server.shutdown()
        server.server_close()


def test_api_watch_reports_detected_agents_and_alerts(watch_server):
    base, _ = watch_server
    data = _get(base + "/api/watch")

    assert "claude-code" in data["detected_agents"]
    assert len(data["sessions"]) == 1

    session = data["sessions"][0]
    assert session["cwd"] == CWD
    rules = [a["rule"] for a in session["alerts"]]
    assert "deleted_assertion" in rules
    deleted = next(a for a in session["alerts"] if a["rule"] == "deleted_assertion")
    assert deleted["severity"] == "critical"


def test_api_watch_picks_up_new_activity_on_poll(watch_server):
    base, home = watch_server
    _get(base + "/api/watch")  # prime the watcher (first poll)

    path = home / ".claude" / "projects" / "C--work-myrepo" / "s1.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_session_line("Bash", {"command": "rm -rf build"}) + "\n")

    data = _get(base + "/api/watch")
    session = data["sessions"][0]
    rules = [a["rule"] for a in session["alerts"]]
    assert "destructive_command" in rules


def test_api_watch_includes_clients(watch_server):
    base, _ = watch_server
    data = _get(base + "/api/watch")

    clients = {c["name"]: c for c in data["clients"]}
    assert "claude-code" in clients
    assert clients["claude-code"]["display"] == "Claude Code"
    assert clients["claude-code"]["parsed"] is True


def test_api_session_returns_steps_for_watched_session(watch_server):
    base, _ = watch_server
    watch_data = _get(base + "/api/watch")
    path = watch_data["sessions"][0]["path"]

    data = _get(base + f"/api/session?path={urllib.parse.quote(path)}")
    assert data["path"] == path
    assert len(data["trajectory"]["steps"]) == 2


def test_api_session_refuses_unwatched_path(watch_server, tmp_path):
    base, _ = watch_server
    _get(base + "/api/watch")  # prime the watcher

    outside = tmp_path / "not-a-session.jsonl"
    outside.write_text("{}\n", encoding="utf-8")

    request = urllib.request.Request(base + f"/api/session?path={urllib.parse.quote(str(outside))}")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request)
    assert excinfo.value.code == 400


def test_api_gate_with_session_path(watch_server):
    base, _ = watch_server
    watch_data = _get(base + "/api/watch")
    path = watch_data["sessions"][0]["path"]

    request = urllib.request.Request(
        base + "/api/gate",
        data=json.dumps({"tasks_dir": "tasks", "session_path": path}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        report = json.loads(response.read().decode("utf-8"))
    assert report["tasks_total"] > 0


def test_api_watch_digest_returns_markdown(watch_server):
    base, _ = watch_server
    _get(base + "/api/watch")  # prime the watcher

    with urllib.request.urlopen(base + "/api/watch/digest") as response:
        body = response.read().decode("utf-8")
        content_type = response.headers.get("Content-Type", "")
        disposition = response.headers.get("Content-Disposition", "")
    assert content_type.startswith("text/markdown")
    assert "attachment" in disposition
    assert "AgentBench Session Digest" in body


def test_api_watch_empty_machine(tmp_path, monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    server = make_server(REPO_ROOT, tasks_dir="tasks", port=0, watch_home=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        data = _get(base + "/api/watch")
        assert data["detected_agents"] == []
        assert data["sessions"] == []
    finally:
        server.shutdown()
        server.server_close()
