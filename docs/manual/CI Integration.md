# CI Integration

AgentBench OS gates pull requests by replaying a recorded agent trajectory
against a directory of task oracles and failing the workflow on any
violation. This page covers the composite GitHub Action that ships in the
repo, a working example workflow, exit codes, and where reports end up.

## What actually runs in CI

The GitHub Action (`action/action.yml`, composite action) does not shell
out to the `agentbench gate` CLI subcommand directly. It runs
`action/entrypoint.py`, a small wrapper around the same
`agentbench.eval.gate.evaluator.Evaluator` class the CLI uses, with one addition
the CLI's `gate` subcommand lacks: it writes a JSON report file and exposes
`passed` / `tasks-passed` / `tasks-failed` as GitHub Action outputs. Either
entry point (`agentbench gate` or `action/entrypoint.py`) gives the same
pass/fail evaluation; only the report file and outputs are action-specific.

## Prerequisites

- Python 3.11+ available in CI (the action installs AgentBench itself via
  `actions/setup-python`)
- A trajectory JSON file - a recorded agent run with tool-call steps (see
  [Writing Oracles](Writing%20Oracles.md#task-and-trajectory-shape))
- Task JSON files, either your own under `.agentbench/tasks/` or the
  defaults shipped in this repo's `tasks/`

## Quick setup

### 1. Copy or generate a workflow

Two templates ship in `examples/dogfood/`:

| Repo type | Template |
|-----------|----------|
| Generic Python project | `examples/dogfood/generic-python-repo-workflow.yml` |
| Infra / k8s (Docker, deploy scripts) | `examples/dogfood/infra-k8s-workflow.yml` |

Or run the setup script from a clone of AgentBench OS, which copies the
right template into your target repo and creates the `.agentbench/`
directory for trajectory storage:

```bash
# Linux / macOS
./scripts/dogfood_setup.sh /path/to/your-repo python

# Windows (PowerShell)
.\scripts\dogfood_setup.ps1 -TargetRepo C:\path\to\your-repo -Template python
```

This writes `.github/workflows/agentbench-gate.yml` and creates
`.agentbench/.gitkeep` plus `.agentbench/tasks/.gitkeep` in the target repo.

### 2. Point the workflow at the action source

Pick one, depending on whether you're vendoring AgentBench into your own
repo or pulling it from GitHub:

**Same monorepo (dogfooding AgentBench itself):**

```yaml
- uses: ./action
  with:
    tasks: tasks
    trajectory: tests/fixtures/trajectory_pass.json
    task-manifest: tasks/manifest_pass.json
```

**External repo, referencing the action directly from GitHub:**

```yaml
- uses: casualstack/agentbench-os/action@main
  with:
    tasks: .agentbench/tasks
    trajectory: .agentbench/last-run.json
```

A third option - checking out `agentbench-os` into the workflow and
referencing `./agentbench-os/action` - works too and needs no publishing
step at all; the complete example below uses exactly that pattern.

### 3. Commit a trajectory

```
your-repo/
  .agentbench/
    last-run.json      # recorded agent session
    tasks/              # optional: repo-specific eval tasks
  .github/workflows/
    agentbench-gate.yml
```

Minimal trajectory shape (full schema in
[Writing Oracles](Writing%20Oracles.md)):

```json
{
  "metadata": { "agent": "cursor", "model": "claude-sonnet-4" },
  "steps": [
    { "type": "tool_call", "tool": "write_file", "args": { "path": "src/foo.py", "content": "..." } }
  ]
}
```

Record trajectories from real sessions by exporting a session's tool calls
to JSONL and feeding it through the Recorder tab in `agentbench ui` (see
[Desktop App](Desktop%20App.md#other-tabs)).

### 4. Open a pull request

The gate job runs and fails with the specific oracle messages when a
regression is detected.

## Workflow inputs

| Input | Default | Description |
|-------|---------|--------------|
| `tasks` | `tasks` | Directory of eval task JSON files |
| `trajectory` | *(required)* | Path to the agent trajectory JSON |
| `task-manifest` | *(empty)* | Optional manifest JSON listing `task_files` compatible with the trajectory |
| `python-version` | `3.11` | Python version for the runner |
| `report-path` | `agentbench-report.json` | Path to write the gate results JSON report |
| `artifact-name` | `agentbench-gate-results` | Name for the uploaded gate results artifact |

## Outputs

| Output | Description |
|--------|--------------|
| `passed` | `"true"` / `"false"` - whether every task passed |
| `tasks-passed` | Number of tasks that passed |
| `tasks-failed` | Number of tasks that failed |

Read from downstream steps as `${{ steps.<step-id>.outputs.passed }}`, etc.
(the action's internal step id is `gate`).

## A complete working example

Adapted from `examples/dogfood/generic-python-repo-workflow.yml`, which
ships in the repo and runs AgentBench alongside a normal pytest job:

```yaml
name: AgentBench Gate

on:
  pull_request:
    paths:
      - "src/**"
      - "tests/**"
      - "pyproject.toml"
      - ".agentbench/**"
  workflow_dispatch:
    inputs:
      trajectory:
        description: Path to agent trajectory JSON
        required: true
        default: .agentbench/last-run.json

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run pytest
        run: python -m pytest -q

  agentbench-gate:
    runs-on: ubuntu-latest
    needs: pytest
    steps:
      - uses: actions/checkout@v4

      - name: Checkout AgentBench OS
        uses: actions/checkout@v4
        with:
          repository: casualstack/agentbench-os
          path: agentbench-os

      - name: Run AgentBench gate
        uses: ./agentbench-os/action
        with:
          tasks: .agentbench/tasks
          trajectory: ${{ github.event.inputs.trajectory || '.agentbench/last-run.json' }}
          python-version: "3.11"
```

`pytest` checks that current code is correct; `agentbench-gate` checks that
the agent's own process was not cutting corners to get there - the two jobs
answer different questions and both matter (see
[Concepts and Glossary](Concepts%20and%20Glossary.md#philosophy) for why
they don't substitute for each other).

## Manual re-runs

Both example workflows in the repo wire up `workflow_dispatch` so you can
re-run the gate against a different trajectory without pushing a commit:

1. GitHub -> Actions -> **AgentBench Gate** -> **Run workflow**
2. Set the `trajectory` input, e.g. `.agentbench/last-run.json`

## Exit codes and blocking merges

`agentbench gate` and the action's entrypoint both exit `1` if any task
fails, or if the tasks directory contains no task JSON files at all, and
`0` only if every task passed. Set the `agentbench-gate` job as a required
status check in branch protection rules to block merges on failure.

## Where reports and artifacts go

The action always writes `report-path` (default `agentbench-report.json`)
after the gate runs, and uploads it as a workflow artifact under
`artifact-name` (default `agentbench-gate-results`) using
`actions/upload-artifact@v4` with `if: always()`, so a failed PR still has
a downloadable report. The report JSON shape:

```json
{
  "passed": true,
  "tasks_total": 6,
  "tasks_passed": 6,
  "tasks_failed": 0,
  "tasks": [
    {
      "task_id": "fix-failing-test-no-delete",
      "passed": true,
      "oracle_results": [
        { "oracle_type": "assertion_exists", "passed": true, "message": "Assertion pattern found in tests/test_calc.py" }
      ]
    }
  ]
}
```

Separately, every gate run through the desktop/browser client is appended
to `.agentbench/history.jsonl` in the project root and viewable in the
client's History tab (see [Desktop App](Desktop%20App.md)) - that history
file is local-only and is not automatically produced by the GitHub Action
itself.

## How this repository gates itself

`.github/workflows/agentbench-gate.yml` in the repo is a working
self-referential example: a `gate-pass` job runs the action against
`tests/fixtures/trajectory_pass.json` and `tasks/manifest_pass.json`,
expected to succeed; a `gate-fail-demo` job runs it against
`tests/fixtures/trajectory_regression.json` with `continue-on-error: true`,
then asserts the step's `outcome` was `"failure"` - a CI job that fails on
purpose to prove the gate catches the regression it's designed to catch.
`.github/workflows/ci.yml` is the separate, ordinary pytest job (matrix
over Python 3.11/3.12) that tests AgentBench's own source, unrelated to the
gate action.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No task JSON files found` | Add `*.json` task files under the `tasks` input path, or copy samples from this repo's `tasks/` |
| `Trajectory file not found` | Confirm the path is committed and matches the workflow's `trajectory` input exactly |
| Gate passes locally, fails in CI | CI runs from a fresh checkout - confirm trajectory and task paths are relative to the repo root, not your local working directory |
| `pip install -e .` fails in the action | The "checkout + local action" option needs AgentBench OS checked out at the path you reference; the "external repo" option needs a real git ref on `casualstack/agentbench-os` reachable from your workflow |

## Related

- [Writing Oracles](Writing%20Oracles.md) - task and trajectory schema referenced above
- [Watch Mode](Watch%20Mode.md) - recording trajectories from real sessions instead of hand-writing them
- [FAQ and Troubleshooting](FAQ%20and%20Troubleshooting.md) - what to do when a gate blocks a PR you believe is correct
