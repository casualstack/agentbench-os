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
render per task with per-oracle pass/fail; failed oracles expand to show full
details (stderr, violations). Same evaluation the GitHub Action runs in CI.

### Tasks
Browse the task JSONs in any directory under the project root. Click a task to
drill into the agent prompt, oracle definitions, and initial workspace files.

### Trajectories
Inspect any recorded run step by step — tool, args, with file edits and shell
commands badged.

### Matrix
Run any discovered benchmark matrix config (`benchmarks/*.yaml`, `configs/*.json`)
and get the cell table, per-model/per-prompt aggregates, and drift-vs-baseline
verdict.

### History
Every gate run is persisted to `.agentbench/history.jsonl` in the project root.
The tab shows a pass-rate trend over recent runs; click a run to re-open its full
report.

### Recorder
Paste JSONL tool-call logs (one JSON object per line, Cursor/Claude Code exports).
Field names like `tool`/`name`/`function` and `args`/`input`/`parameters` are
normalized automatically. Download the result as `trajectory.json` or send it
straight to the gate runner.

## HTTP API

The client is a thin frontend over a local JSON API (all paths resolved
relative to `--root` and confined to it):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/root` | GET/POST | Get or switch the project root |
| `/api/tasks?dir=tasks` | GET | List task files in a directory |
| `/api/task?dir=&file=` | GET | Full task definition |
| `/api/trajectories` | GET | Discover trajectory JSONs |
| `/api/trajectory?path=` | GET | Full trajectory (validated) |
| `/api/gate` | POST | Run the gate: `{tasks_dir, trajectory_path \| trajectory, manifest?}` |
| `/api/matrix-configs` | GET | Discover benchmark matrix configs |
| `/api/matrix` | POST | Run a matrix: `{config}` |
| `/api/history` | GET | Recent gate runs (from `.agentbench/history.jsonl`) |
| `/api/record` | POST | Convert JSONL: `{jsonl, agent?, model?, source?}` |

## Security notes

- Binds to `127.0.0.1` only; requests with a non-localhost `Host` header are rejected.
- Request paths are confined to the project root (no `../` escapes).
- `test_must_pass` oracles execute the shell commands defined in your local task
  JSONs — same trust model as running `agentbench gate` in a terminal.
