"""Local HTTP server backing the AgentBench dashboard.

Binds to 127.0.0.1 only. All file paths in API requests are resolved
relative to the project root and confined to it.
"""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from agentbench.gate.evaluator import Evaluator
from agentbench.gate.manifest import load_task_manifest
from agentbench.matrix import MatrixConfig, MatrixRunner, detect_score_drift
from agentbench.models.task import EvalTask, RunResult
from agentbench.recorder import build_trajectory, steps_from_jsonl
from agentbench.runner.trajectory import Trajectory
from agentbench.watch.watcher import SessionWatcher

STATIC_DIR = Path(__file__).parent / "static"
HISTORY_LIMIT = 50

# Matrix configs resolve trajectory/task paths relative to the process cwd,
# so matrix runs chdir to the project root; serialize them.
_MATRIX_LOCK = threading.Lock()

# The SessionWatcher is shared across requests (one per server) and isn't
# safe for concurrent poll()/sessions() calls; ThreadingHTTPServer handles
# requests on separate threads, so guard both creation and use.
_WATCH_LOCK = threading.Lock()


def _resolve_under(root: Path, candidate: str) -> Path:
    """Resolve a request-supplied path, refusing anything outside root."""
    path = (root / candidate).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"path escapes project root: {candidate}")
    return path


def _result_to_dict(result: RunResult) -> dict[str, Any]:
    return {
        "task_id": result.task_id,
        "passed": result.passed,
        "oracle_results": [
            {
                "oracle_type": r.oracle_type,
                "passed": r.passed,
                "message": r.message,
                "details": r.details,
            }
            for r in result.oracle_results
        ],
    }


def _gate_report(results: list[RunResult]) -> dict[str, Any]:
    failed = sum(1 for r in results if not r.passed)
    return {
        "passed": failed == 0,
        "tasks_total": len(results),
        "tasks_passed": len(results) - failed,
        "tasks_failed": failed,
        "tasks": [_result_to_dict(r) for r in results],
    }


def _task_summary(path: Path, task: EvalTask) -> dict[str, Any]:
    return {
        "file": path.name,
        "id": task.id,
        "name": task.name,
        "description": task.description,
        "tags": task.tags,
        "oracles": [o.type for o in task.oracles],
    }


class UIHandler(BaseHTTPRequestHandler):
    """Request handler; ``root`` and ``tasks_dir`` are set by make_server."""

    root: Path
    tasks_dir: str
    # Override in tests to point session discovery at a tmp dir instead of
    # the real ~/.claude/projects.
    watch_home: Path | None = None
    _watcher: SessionWatcher | None = None

    # -- plumbing ---------------------------------------------------------

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # keep the terminal quiet; errors surface in responses

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._send_json({"error": message}, status)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            raise ValueError("empty request body")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def _host_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    # -- routes -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_allowed():
            self._send_error_json("forbidden host", HTTPStatus.FORBIDDEN)
            return

        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path in ("/", "/index.html"):
                self._serve_index()
            elif parsed.path == "/api/root":
                self._send_json({"root": str(self.root)})
            elif parsed.path == "/api/tasks":
                self._api_tasks(query)
            elif parsed.path == "/api/task":
                self._api_task_detail(query)
            elif parsed.path == "/api/trajectories":
                self._api_trajectories()
            elif parsed.path == "/api/trajectory":
                self._api_trajectory_detail(query)
            elif parsed.path == "/api/matrix-configs":
                self._api_matrix_configs()
            elif parsed.path == "/api/history":
                self._api_history()
            elif parsed.path == "/api/watch":
                self._api_watch()
            else:
                self._send_error_json("not found", HTTPStatus.NOT_FOUND)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._send_error_json(str(exc))

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_allowed():
            self._send_error_json("forbidden host", HTTPStatus.FORBIDDEN)
            return

        try:
            if self.path == "/api/gate":
                self._api_gate(self._read_json_body())
            elif self.path == "/api/record":
                self._api_record(self._read_json_body())
            elif self.path == "/api/root":
                self._api_set_root(self._read_json_body())
            elif self.path == "/api/matrix":
                self._api_matrix(self._read_json_body())
            else:
                self._send_error_json("not found", HTTPStatus.NOT_FOUND)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._send_error_json(str(exc))

    # -- handlers ---------------------------------------------------------

    def _serve_index(self) -> None:
        body = (STATIC_DIR / "index.html").read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_tasks(self, query: dict[str, list[str]]) -> None:
        tasks_dir = query.get("dir", [self.tasks_dir])[0]
        try:
            directory = _resolve_under(self.root, tasks_dir)
        except ValueError as exc:
            self._send_error_json(str(exc))
            return

        tasks = []
        manifests = []
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                try:
                    tasks.append(_task_summary(path, EvalTask.from_file(path)))
                except (ValueError, KeyError):
                    manifests.append(path.name)  # manifest or non-task JSON

        self._send_json({"dir": tasks_dir, "tasks": tasks, "manifests": manifests})

    def _api_trajectories(self) -> None:
        found = []
        for pattern in ("tests/fixtures/*.json", ".agentbench/*.json"):
            for path in sorted(self.root.glob(pattern)):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict) and isinstance(data.get("steps"), list):
                    found.append(
                        {
                            "path": path.relative_to(self.root).as_posix(),
                            "steps": len(data["steps"]),
                            "metadata": data.get("metadata", {}),
                        }
                    )
        self._send_json({"trajectories": found})

    def _api_gate(self, body: dict[str, Any]) -> None:
        tasks_dir = _resolve_under(self.root, body.get("tasks_dir", self.tasks_dir))

        if "trajectory" in body:
            trajectory = Trajectory.from_dict(body["trajectory"])
            trajectory_label = "(pasted trajectory)"
        elif "trajectory_path" in body:
            trajectory = Trajectory.from_file(
                _resolve_under(self.root, body["trajectory_path"])
            )
            trajectory_label = body["trajectory_path"]
        else:
            raise ValueError("provide 'trajectory' (object) or 'trajectory_path'")

        task_files = None
        if body.get("manifest"):
            task_files = load_task_manifest(_resolve_under(self.root, body["manifest"]))

        if task_files:
            task_paths = [tasks_dir / name for name in task_files]
        else:
            task_paths = sorted(
                p for p in tasks_dir.glob("*.json") if p.name != "manifest_pass.json"
            )

        evaluator = Evaluator()
        results = [
            evaluator.evaluate(EvalTask.from_file(p), trajectory) for p in task_paths
        ]
        report = _gate_report(results)
        self._append_history(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "trajectory": trajectory_label,
                "tasks_dir": body.get("tasks_dir", self.tasks_dir),
                "manifest": body.get("manifest") or None,
                "report": report,
            }
        )
        self._send_json(report)

    # -- history ------------------------------------------------------------

    def _history_file(self) -> Path:
        return self.root / ".agentbench" / "history.jsonl"

    def _append_history(self, record: dict[str, Any]) -> None:
        try:
            path = self._history_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        except OSError:
            pass  # history is best-effort; never fail a gate run over it

    def _api_history(self) -> None:
        runs: list[dict[str, Any]] = []
        path = self._history_file()
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    runs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        self._send_json({"runs": runs[-HISTORY_LIMIT:][::-1]})

    # -- watch ----------------------------------------------------------------

    def _api_watch(self) -> None:
        """Poll the shared session watcher and return its current snapshot.

        Watches every session on the machine (no project filter) so the
        dashboard shows agent activity regardless of which project is open;
        the first poll includes session history, not just new activity.
        """
        cls = type(self)
        with _WATCH_LOCK:
            if cls._watcher is None:
                cls._watcher = SessionWatcher(home=cls.watch_home, skip_existing=False)
            cls._watcher.poll()
            payload = {
                "detected_agents": cls._watcher.detected_agents(),
                "sessions": cls._watcher.sessions(),
            }
        self._send_json(payload)

    # -- detail views ---------------------------------------------------------

    def _api_task_detail(self, query: dict[str, list[str]]) -> None:
        tasks_dir = query.get("dir", [self.tasks_dir])[0]
        file_name = query.get("file", [""])[0]
        if not file_name:
            raise ValueError("provide 'file'")
        path = _resolve_under(self.root, f"{tasks_dir}/{file_name}")
        data = json.loads(path.read_text(encoding="utf-8"))
        self._send_json({"file": file_name, "task": data})

    def _api_trajectory_detail(self, query: dict[str, list[str]]) -> None:
        rel = query.get("path", [""])[0]
        if not rel:
            raise ValueError("provide 'path'")
        path = _resolve_under(self.root, rel)
        data = json.loads(path.read_text(encoding="utf-8"))
        Trajectory.from_dict(data)  # validate before echoing
        self._send_json({"path": rel, "trajectory": data})

    # -- matrix ---------------------------------------------------------------

    def _api_matrix_configs(self) -> None:
        configs = []
        for pattern in ("benchmarks/*.yaml", "benchmarks/*.yml", "configs/*.json"):
            for path in sorted(self.root.glob(pattern)):
                try:
                    config = MatrixConfig.from_file(path)
                except (ValueError, KeyError, OSError):
                    continue
                configs.append(
                    {
                        "path": path.relative_to(self.root).as_posix(),
                        "name": getattr(config, "name", path.stem) or path.stem,
                        "cells": len(config.cells),
                        "has_baseline": config.baseline is not None,
                    }
                )
        self._send_json({"configs": configs})

    def _api_matrix(self, body: dict[str, Any]) -> None:
        config_path = body.get("config")
        if not isinstance(config_path, str) or not config_path:
            raise ValueError("provide 'config' path")
        config = MatrixConfig.from_file(_resolve_under(self.root, config_path))

        with _MATRIX_LOCK:
            cwd = os.getcwd()
            os.chdir(self.root)
            try:
                result = MatrixRunner().run(config)
                payload = result.model_dump(mode="json")
                if config.baseline is not None:
                    drift = detect_score_drift(
                        result, config.baseline, threshold=config.drift_threshold
                    )
                    payload["drift"] = drift.model_dump(mode="json")
            finally:
                os.chdir(cwd)
        self._send_json(payload)

    def _api_set_root(self, body: dict[str, Any]) -> None:
        """Switch the project root (desktop client 'open project')."""
        raw = body.get("path")
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("provide 'path'")
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"not a directory: {raw}")
        type(self).root = path
        self._send_json({"root": str(path)})

    def _api_record(self, body: dict[str, Any]) -> None:
        jsonl = body.get("jsonl")
        if not isinstance(jsonl, str) or not jsonl.strip():
            raise ValueError("provide 'jsonl' text")

        steps = steps_from_jsonl(jsonl)
        metadata = {
            key: body[key]
            for key in ("agent", "model", "source")
            if isinstance(body.get(key), str) and body[key]
        }
        self._send_json(build_trajectory(steps, metadata))


def make_server(
    root: Path | str = ".",
    *,
    tasks_dir: str = "tasks",
    port: int = 0,
    watch_home: Path | str | None = None,
) -> ThreadingHTTPServer:
    """Create a dashboard server bound to 127.0.0.1 (port 0 = ephemeral).

    ``watch_home`` overrides where the live-watch feature looks for agent
    session logs (``<watch_home>/.claude/projects``); tests point this at a
    tmp dir, real usage leaves it as ``None`` to use the user's home.
    """
    handler = type(
        "BoundUIHandler",
        (UIHandler,),
        {
            "root": Path(root).resolve(),
            "tasks_dir": tasks_dir,
            "watch_home": Path(watch_home) if watch_home is not None else None,
            "_watcher": None,
        },
    )
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(
    root: Path | str = ".",
    *,
    tasks_dir: str = "tasks",
    port: int = 8321,
    open_browser: bool = True,
) -> int:
    """Run the dashboard until interrupted."""
    server = make_server(root, tasks_dir=tasks_dir, port=port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"AgentBench dashboard: {url} (Ctrl+C to stop)")

    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0
