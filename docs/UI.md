# AgentBench Client (`agentbench app` / `agentbench ui`)

An all-in-one client bundled with the package: live session watch, gate runner,
trajectory diffing, task browser, and trajectory recorder.

## Desktop app

Native window, no browser needed:

```bash
pip install -e ".[app]"      # adds pywebview
agentbench app               # opens the AgentBench window
agentbench app --root /path/to/target-repo
```

Use **Browse…** in the header to open any project folder; the whole client
(tasks, trajectories, gate runs) re-targets to it.

### Download / build the desktop app

AgentBench ships standalone builds for Windows, macOS, and Linux — no Python
install required to run them.

**Download a build:** every tagged release (`vX.Y.Z`) attaches zipped builds
for all three platforms to the [GitHub release](../../releases). A build from
any commit is also available as a CI artifact: open the
[Desktop Builds workflow run](../../actions/workflows/desktop-builds.yml) for
that commit and download `AgentBench-windows`, `AgentBench-macos`, or
`AgentBench-linux`.

**Build locally:**

```powershell
# Windows
pip install -e ".[app]" pyinstaller
.\scripts\build_desktop.ps1    # → dist\AgentBench.exe
```

```bash
# macOS / Linux
pip install -e ".[app]" pyinstaller
./scripts/build_desktop.sh     # → dist/AgentBench.app (macOS) or dist/AgentBench (Linux)
```

Both scripts just invoke PyInstaller against `AgentBench.spec` — the spec is
the single source of truth for build options (icon, version resource,
one-dir layout), same as the CI build. Linux additionally needs pywebview's
GTK backend system packages (GObject introspection + WebKitGTK) — see the
`apt-get install` step in `.github/workflows/desktop-builds.yml` for the
current package list.

The build output is a folder (`dist/AgentBench/`), not a single exe — see
below for why.

### Windows says it "protected your PC"?

That's Windows SmartScreen, and it's expected: AgentBench's desktop builds
aren't signed with an Authenticode certificate yet, and SmartScreen warns on
any unsigned binary regardless of what it does. Click **More info**, then
**Run anyway** — but only if you got the build from the
[official GitHub release](../../releases) or a
[CI artifact](../../actions/workflows/desktop-builds.yml) you trust. macOS
Gatekeeper shows an equivalent warning for the unsigned `.app`; right-click
it and choose **Open** to bypass it once.

If you'd rather avoid the warning entirely, build from source (above) — a
build you compiled yourself has nothing to be flagged.

Two build choices already reduce false positives: the build is one-dir
(not one-file), since a self-extracting one-file exe is exactly the pattern
SmartScreen's heuristics distrust; and it embeds a real version resource
(`AgentBench.version.txt`) instead of shipping with none.

**Not done yet:** buying an Authenticode/EV code-signing certificate and
adding a `signtool` step to `.github/workflows/desktop-builds.yml` (plus
setting `codesign_identity` in `AgentBench.spec` for macOS) would remove the
warning altogether. Tracked as follow-up work, not implemented in this repo
yet.

## Browser mode

The same client served to a browser tab:

```bash
agentbench ui                 # serves http://127.0.0.1:8321 and opens a tab
agentbench ui --port 9000 --no-browser
agentbench ui --root /path/to/target-repo --tasks .agentbench/tasks
```

## Tabs

### Live watch
Auto-detects local AI coding sessions (Claude Code, Cursor, and Codex CLI
fully parsed; Antigravity detected, parsing coming) and continuously surfaces
accountability alerts in plain English — nothing to import. A stat strip
summarizes session/critical/warning counts and per-client chips; **Download
report** exports the same summary as a shareable markdown file. Includes
default guards like deleted assertions, skipped tests, out-of-project writes,
destructive commands, privilege escalation patterns, potential secret exposure,
possible data exfiltration commands, and CI/policy-file edits.

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

### Diff
Compare two recorded trajectories and get a git-like accountability diff:
step count delta, tool usage added/removed, files newly touched/no longer
touched, and command deltas.

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
| `/api/watch` | GET | Poll session watcher; current sessions, alerts, and detected `clients` |
| `/api/watch/digest` | GET | Download the current watch snapshot as a markdown report |
| `/api/session?path=` | GET | Parse one watched session (path must be one the watcher discovered) |
| `/api/diff` | POST | Compare two trajectories: `{baseline_path, candidate_path}` |
| `/api/gate` | POST | Run the gate: `{tasks_dir, trajectory_path \| trajectory \| session_path, manifest?}` |
| `/api/matrix-configs` | GET | Discover benchmark matrix configs |
| `/api/matrix` | POST | Run a matrix: `{config}` |
| `/api/history` | GET | Recent gate runs (from `.agentbench/history.jsonl`) |
| `/api/record` | POST | Convert JSONL: `{jsonl, agent?, model?, source?}` |

## Security notes

- Binds to `127.0.0.1` only; requests with a non-localhost `Host` header are rejected.
- Request paths are confined to the project root (no `../` escapes).
- `/api/session` and `/api/gate`'s `session_path` are the one exception to
  root-confinement: session logs live outside the project root (e.g.
  `~/.claude/projects`), so they can't be checked against it. Instead, both
  only ever parse a path that appears in the watcher's own `sessions()`
  snapshot — an allowlist built from what was actually discovered on this
  machine, never an arbitrary caller-supplied path.
- `test_must_pass` oracles execute the shell commands defined in your local task
  JSONs — same trust model as running `agentbench gate` in a terminal.
