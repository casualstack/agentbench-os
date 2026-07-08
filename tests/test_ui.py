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
