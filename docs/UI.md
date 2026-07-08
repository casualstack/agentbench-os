# AgentBench Client (`agentbench app` / `agentbench ui`)

An all-in-one client bundled with the package: gate runner, task browser, and
trajectory recorder.

## Desktop app

Native window, no browser needed:

```bash
pip install -e ".[app]"      # adds pywebview
agentbench app               # opens the AgentBench window
agentbench app --root /path/to/target-repo
```

Use **Browse…** in the header to open any project folder; the whole client
(tasks, trajectories, gate runs) re-targets to it.

Build a standalone `AgentBench.exe` (Windows):

```powershell
pip install -e ".[app]" pyinstaller
.\scripts\build_desktop.ps1    # → dist\AgentBench.exe
```

## Browser mode

The same client served to a browser tab:

```bash
agentbench ui                 # serves http://127.0.0.1:8321 and opens a tab
agentbench ui --port 9000 --no-browser
agentbench ui --root /path/to/target-repo --tasks .agentbench/tasks
```

## Tabs

### Gate runner
Pick a discovered trajectory (from `tests/fixtures/` or `.agentbench/`) or paste a
trajectory JSON, optionally limit tasks with a manifest, and run the gate. Results
render per task with per-oracle pass/fail and failure messages — the same
evaluation the GitHub Action runs in CI.

### Tasks
Browse the task JSONs in any directory under the project root: id, name, oracle
types, and tags.

### Recorder
Paste JSONL tool-call logs (one JSON object per line, Cursor/Claude Code exports).
Field names like `tool`/`name`/`function` and `args`/`input`/`parameters` are
normalized automatically. Download the result as `trajectory.json` or send it
straight to the gate runner.

## HTTP API

The dashboard is a thin frontend over a local JSON API (all paths resolved
relative to `--root` and confined to it):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tasks?dir=tasks` | GET | List task files in a directory |
| `/api/trajectories` | GET | Discover trajectory JSONs |
| `/api/gate` | POST | Run the gate: `{tasks_dir, trajectory_path \| trajectory, manifest?}` |
| `/api/record` | POST | Convert JSONL: `{jsonl, agent?, model?, source?}` |

## Security notes

- Binds to `127.0.0.1` only; requests with a non-localhost `Host` header are rejected.
- Request paths are confined to the project root (no `../` escapes).
- `test_must_pass` oracles execute the shell commands defined in your local task
  JSONs — same trust model as running `agentbench gate` in a terminal.
