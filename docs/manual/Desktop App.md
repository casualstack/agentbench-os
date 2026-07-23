# Desktop App

The AgentBench client is an all-in-one interface bundled with the package:
live session watch, gate runner, trajectory diffing, task browser, and a
trajectory recorder, all served from a local JSON API. It ships two ways to
run it - a native desktop window and a browser tab - both backed by the
exact same server and API.

## App versus CLI

The CLI (`agentbench run` / `gate` / `watch` / `diff` / `matrix`) is the
scriptable, CI-facing surface - see [Quickstart](Quickstart.md),
[CI Integration](CI%20Integration.md), and [Watch Mode](Watch%20Mode.md).
The desktop/browser client is a local dashboard over the same evaluation
engine, for exploring tasks, trajectories, and watch alerts interactively
instead of one command at a time. Nothing in the client talks to a remote
server; it is a thin frontend over a local HTTP API bound to
`127.0.0.1`.

## Getting it

### Native window

```bash
pip install -e ".[app]"      # adds pywebview
agentbench app                # opens the AgentBench window
agentbench app --root /path/to/target-repo
```

`--root` sets which project the client starts pointed at (default `.`);
use **Browse...** in the header at any time to open a different project
folder - the whole client (tasks, trajectories, gate runs) re-targets to
it without restarting.

### Browser tab

The identical client served over HTTP, no native window dependency needed:

```bash
agentbench ui                                        # serves http://127.0.0.1:8321 and opens a tab
agentbench ui --port 9000 --no-browser
agentbench ui --root /path/to/target-repo --tasks .agentbench/tasks
```

| Flag | Default | Description |
|------|---------|--------------|
| `--root PATH` | `.` | Project root the dashboard reads tasks/trajectories from |
| `--tasks PATH` | `tasks` | Tasks directory (relative to `--root`) |
| `--port PORT` | `8321` | Port on `127.0.0.1` |
| `--no-browser` | off | Do not auto-open a browser tab |

### Prebuilt downloads

Standalone builds for Windows, macOS, and Linux need no local Python
install. Every tagged release attaches a zipped build for each platform to
the GitHub releases page:
https://github.com/casualstack/agentbench-os/releases

A build from any commit is also available as a CI artifact from the
`Desktop Builds` workflow - open that workflow run for the commit you want
and download `AgentBench-windows`, `AgentBench-macos`, or
`AgentBench-linux`. Full build instructions (including building from
source yourself) are in [Installation](Installation.md#desktop-app-builds).

## Live watch UX

The Live Watch tab auto-detects local AI coding sessions the same way
`agentbench watch` does - Claude Code and Codex CLI fully parsed and live
tailed, Cursor parsed best-effort, Antigravity detected only - and
continuously surfaces accountability alerts in plain English; nothing to
import. A stat strip on top summarizes session count, critical count, and
warning count, with per-client chips showing which agents were found.
**Download report** exports the same summary the CLI's `--digest` writes,
as a shareable markdown file (source: `render_digest()` in
`src/agentbench/accountability/digest.py`, served at `/api/watch/digest`). Guards
shown here are the same fixed rule set covered in
[Watch Mode](Watch%20Mode.md#default-rules).

## Other tabs

**Gate runner.** Pick a discovered trajectory (from `tests/fixtures/` or
`.agentbench/`) or paste one directly, optionally scope to a manifest, and
run the gate. Results render per task with per-oracle pass/fail; a failed
oracle expands to full detail (stderr, violations) - the same evaluation
the GitHub Action runs in CI (see [CI Integration](CI%20Integration.md)).

**Tasks.** Browse task JSONs under any directory in the project root.
Click one to see the prompt, oracle definitions, and initial workspace
files - the same fields documented in
[Writing Oracles](Writing%20Oracles.md).

**Trajectories.** Inspect any recorded run step by step: tool, arguments,
file edits and shell commands badged for quick scanning.

**Diff.** The same git-like accountability diff `agentbench diff` produces
on the command line: step count delta, tool usage added/removed, files
newly touched or no longer touched, and command deltas.

**Matrix.** Run any discovered benchmark matrix config
(`benchmarks/*.yaml`, `configs/*.json`) and see the cell table, per-model
and per-prompt aggregates, and a drift-versus-baseline verdict.

**History.** Every gate run is appended to `.agentbench/history.jsonl` in
the project root. This tab shows a pass-rate trend over recent runs; click
any run to reopen its full report.

**Recorder.** Paste JSONL tool-call logs (one JSON object per line -
Cursor/Claude Code style exports). Field names like `tool`/`name`/
`function` and `args`/`input`/`parameters` normalize automatically (source:
`src/agentbench/recorder.py`). Download the result as `trajectory.json` or
send it straight into the gate runner tab.

## HTTP API

The client is a thin frontend over a local JSON API. Every path is
resolved relative to `--root` and confined to it.

| Endpoint | Method | Description |
|----------|--------|--------------|
| `/api/root` | GET/POST | Get or switch the project root |
| `/api/tasks?dir=tasks` | GET | List task files in a directory |
| `/api/task?dir=&file=` | GET | Full task definition |
| `/api/trajectories` | GET | Discover trajectory JSONs |
| `/api/trajectory?path=` | GET | Full trajectory (validated) |
| `/api/watch` | GET | Poll the session watcher: current sessions, alerts, detected `clients` |
| `/api/watch/digest` | GET | Download the current watch snapshot as a markdown report |
| `/api/session?path=` | GET | Parse one watched session (path must be one the watcher discovered) |
| `/api/diff` | POST | Compare two trajectories: `{baseline_path, candidate_path}` |
| `/api/gate` | POST | Run the gate: `{tasks_dir, trajectory_path \| trajectory \| session_path, manifest?}` |
| `/api/matrix-configs` | GET | Discover benchmark matrix configs |
| `/api/matrix` | POST | Run a matrix: `{config}` |
| `/api/history` | GET | Recent gate runs from `.agentbench/history.jsonl` |
| `/api/record` | POST | Convert JSONL: `{jsonl, agent?, model?, source?}` |

## Security notes

- Binds to `127.0.0.1` only; requests carrying a non-localhost `Host`
  header are rejected.
- Request paths are confined to the project root - no `../` escapes.
- `/api/session` and `/api/gate`'s `session_path` are the one exception to
  root confinement: session logs live outside the project root (e.g.
  `~/.claude/projects`), so they can't be checked against it. Instead both
  only ever parse a path that appears in the watcher's own `sessions()`
  snapshot - an allowlist built from what was actually discovered on this
  machine, never an arbitrary caller-supplied path.
- `test_must_pass` oracles execute shell commands defined in your local
  task JSONs when run through the Gate runner tab - the same trust model as
  running `agentbench gate` in a terminal. The client does not sandbox
  oracle command execution beyond what running it locally already implies.

## Platform notes

- **Windows / macOS unsigned-binary warnings.** Prebuilt desktop downloads
  are not code-signed as of v0.1.0; SmartScreen and Gatekeeper will warn on
  first run. See
  [Installation](Installation.md#windows-smartscreen-and-macos-gatekeeper-warnings).
- **Linux build dependencies.** Building a Linux build locally needs
  pywebview's GTK backend (GObject introspection and WebKitGTK); see the
  package list in [Installation](Installation.md#desktop-app-builds).
- **One-dir, not one-file.** Desktop builds ship as a folder
  (`dist/AgentBench/` on Windows/Linux, `dist/AgentBench.app` on macOS), not
  a single self-extracting executable - a deliberate choice to reduce
  unsigned-binary false positives.

## Related

- [Installation](Installation.md) - full build/download instructions and the SmartScreen/Gatekeeper explanation
- [Watch Mode](Watch%20Mode.md) - the underlying watch engine, adapters, and rule set the Live Watch tab surfaces
- [CI Integration](CI%20Integration.md) - the same gate evaluation, run non-interactively in CI
