"""Tests for the live-watch endpoints on the dashboard server."""

from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from agentbench.accountability.audit import AuditStore
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


# -- audit trail / incidents ---------------------------------------------------


def _audit_record(**overrides):
    record = {
        "ts": "2026-07-15T00:00:00Z",
        "agent": "claude-code",
        "session_id": "s1",
        "cwd": CWD,
        "model": "claude-x",
        "step_index": 0,
        "rule": "deleted_assertion",
        "severity": "critical",
        "title": "Deleted a test assertion",
        "detail": "The agent removed a check.",
        "path": "tests/test_calc.py",
        "source_path": None,
        "source_size": None,
        "source_mtime": None,
    }
    record.update(overrides)
    return record


@pytest.fixture
def audit_server(tmp_path):
    db_path = tmp_path / "audit.db"
    with AuditStore(db_path) as store:
        store.append(_audit_record())
        store.append(_audit_record(step_index=1, rule="skipped_test", severity="critical"))

    server = make_server(REPO_ROOT, tasks_dir="tasks", port=0, audit_db=db_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", db_path
    server.shutdown()
    server.server_close()


def test_api_incidents_lists_synced_incidents(audit_server):
    base, _ = audit_server
    data = _get(base + "/api/incidents")

    assert len(data["incidents"]) == 2
    rules = {i["rule"] for i in data["incidents"]}
    assert rules == {"deleted_assertion", "skipped_test"}
    assert all(i["status"] == "open" for i in data["incidents"])


def test_api_incidents_filters_by_status(audit_server):
    base, db_path = audit_server

    from agentbench.accountability.audit import IncidentStore

    with IncidentStore(db_path) as store:
        [first, _second] = store.list()
        store.resolve(first.incident_id)

    open_data = _get(base + "/api/incidents?status=open")
    resolved_data = _get(base + "/api/incidents?status=resolved")
    assert len(open_data["incidents"]) == 1
    assert len(resolved_data["incidents"]) == 1


def test_api_incidents_empty_db(tmp_path):
    server = make_server(REPO_ROOT, tasks_dir="tasks", port=0, audit_db=tmp_path / "audit.db")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        data = _get(base + "/api/incidents")
        assert data["incidents"] == []
    finally:
        server.shutdown()
        server.server_close()


def test_api_audit_verify_ok(audit_server):
    base, _ = audit_server
    data = _get(base + "/api/audit/verify")
    assert data["ok"] is True
    assert data["broken_event_id"] is None


def test_api_audit_verify_reports_broken_chain(audit_server):
    base, db_path = audit_server

    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE events SET detail = 'edited' WHERE id = 1")
    conn.commit()
    conn.close()

    data = _get(base + "/api/audit/verify")
    assert data["ok"] is False
    assert data["broken_event_id"] == 1
