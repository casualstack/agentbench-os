"""Tests for the local dashboard server (agentbench ui)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from agentbench.ui.server import make_server

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def ui_base_url():
    server = make_server(REPO_ROOT, tasks_dir="tasks", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _get(url: str) -> dict:
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def test_index_served(ui_base_url):
    with urllib.request.urlopen(ui_base_url + "/") as response:
        body = response.read().decode("utf-8")
    assert "AgentBench" in body


def test_static_logo_served(ui_base_url):
    with urllib.request.urlopen(ui_base_url + "/static/agentbench-logo.png") as response:
        payload = response.read()
        content_type = response.headers.get("Content-Type", "")
    assert payload
    assert content_type.startswith("image/")


def test_api_tasks_lists_task_files(ui_base_url):
    data = _get(ui_base_url + "/api/tasks?dir=tasks")
    ids = [t["id"] for t in data["tasks"]]
    assert "fix-failing-test-no-delete" in ids
    assert "manifest_pass.json" in data["manifests"]


def test_api_trajectories_finds_fixtures(ui_base_url):
    data = _get(ui_base_url + "/api/trajectories")
    paths = [t["path"] for t in data["trajectories"]]
    assert "tests/fixtures/trajectory_pass.json" in paths


def test_api_gate_pass(ui_base_url):
    report = _post(
        ui_base_url + "/api/gate",
        {
            "tasks_dir": "tasks",
            "trajectory_path": "tests/fixtures/trajectory_pass.json",
            "manifest": "tasks/manifest_pass.json",
        },
    )
    assert report["passed"] is True
    assert report["tasks_failed"] == 0
    assert report["tasks_total"] > 0


def test_api_gate_rejects_escaping_path(ui_base_url):
    request = urllib.request.Request(
        ui_base_url + "/api/gate",
        data=json.dumps(
            {"trajectory_path": "../../outside.json", "tasks_dir": "tasks"}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request)
    assert excinfo.value.code == 400


def test_api_root_switch(tmp_path):
    server = make_server(REPO_ROOT, tasks_dir="tasks", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert _get(base + "/api/root")["root"] == str(REPO_ROOT)
        switched = _post(base + "/api/root", {"path": str(tmp_path)})
        assert switched["root"] == str(tmp_path.resolve())
        assert _get(base + "/api/root")["root"] == str(tmp_path.resolve())
    finally:
        server.shutdown()
        server.server_close()


def test_api_task_detail(ui_base_url):
    data = _get(ui_base_url + "/api/task?dir=tasks&file=01_fix_failing_test_no_delete.json")
    assert data["task"]["id"] == "fix-failing-test-no-delete"
    assert "prompt" in data["task"]
    assert "workspace" in data["task"]


def test_api_trajectory_detail(ui_base_url):
    data = _get(
        ui_base_url + "/api/trajectory?path=tests/fixtures/trajectory_pass.json"
    )
    assert data["path"] == "tests/fixtures/trajectory_pass.json"
    assert isinstance(data["trajectory"]["steps"], list)


def test_api_matrix_configs(ui_base_url):
    data = _get(ui_base_url + "/api/matrix-configs")
    paths = [c["path"] for c in data["configs"]]
    assert "benchmarks/matrix.yaml" in paths
    fixture = next(c for c in data["configs"] if c["path"] == "benchmarks/matrix.yaml")
    assert fixture["cells"] == 4
    assert fixture["has_baseline"] is True


def test_api_diff(ui_base_url):
    report = _post(
        ui_base_url + "/api/diff",
        {
            "baseline_path": "tests/fixtures/trajectory_pass.json",
            "candidate_path": "tests/fixtures/trajectory_regression.json",
        },
    )
    assert report["changed"] is True
    assert report["added_files"] or report["removed_files"] or report["added_commands"]


def test_gate_run_recorded_in_history(ui_base_url):
    _post(
        ui_base_url + "/api/gate",
        {
            "tasks_dir": "tasks",
            "trajectory_path": "tests/fixtures/trajectory_pass.json",
            "manifest": "tasks/manifest_pass.json",
        },
    )
    data = _get(ui_base_url + "/api/history")
    assert data["runs"], "expected at least one recorded run"
    latest = data["runs"][0]
    assert latest["trajectory"] == "tests/fixtures/trajectory_pass.json"
    assert latest["report"]["passed"] is True
    assert latest["timestamp"]


def test_api_record_normalizes_jsonl(ui_base_url):
    jsonl = "\n".join(
        [
            '{"tool": "run_command", "args": {"command": "pytest -q"}}',
            '{"name": "Write", "input": {"path": "src/calc.py", "content": "x = 1"}}',
        ]
    )
    trajectory = _post(
        ui_base_url + "/api/record",
        {"jsonl": jsonl, "agent": "test-agent"},
    )
    assert len(trajectory["steps"]) == 2
    assert trajectory["steps"][1]["tool"] == "Write"
    assert trajectory["metadata"]["agent"] == "test-agent"
