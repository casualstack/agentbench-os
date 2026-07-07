# GitHub Action — 5-minute setup

Add AgentBench as a PR gate on any repo in about five minutes. The gate replays a recorded agent trajectory and fails the workflow when property oracles detect regressions (deleted assertions, scope creep, network calls, failing tests).

## Prerequisites

- Python **3.11+** in CI (the composite action installs AgentBench for you)
- A **trajectory JSON** file — a recorded agent run with tool-call steps (see [Eval DSL](EVAL_DSL.md))
- Optional: eval **task JSON** files in your repo, or use the defaults from AgentBench OS

## Quick setup (consumer repo)

### 1. Choose a workflow template

| Repo type | Copy from |
|-----------|-----------|
| Infra / k8s (Docker, deploy scripts) | [`examples/dogfood/infra-k8s-workflow.yml`](../examples/dogfood/infra-k8s-workflow.yml) |
| Generic Python project | [`examples/dogfood/generic-python-repo-workflow.yml`](../examples/dogfood/generic-python-repo-workflow.yml) |

Or run the setup script from a clone of AgentBench OS:

```bash
# Linux / macOS
./scripts/dogfood_setup.sh /path/to/your-repo python

# Windows (PowerShell)
.\scripts\dogfood_setup.ps1 -TargetRepo C:\path\to\your-repo -Template python
```

This copies the workflow to `.github/workflows/agentbench-gate.yml` and creates `.agentbench/` for trajectory storage.

### 2. Pin the action source

In your workflow, reference AgentBench OS. Pick one:

**Option A — same monorepo (dogfooding AgentBench itself):**

```yaml
- uses: ./action
  with:
    tasks: tasks
    trajectory: tests/fixtures/trajectory_pass.json
    task-manifest: tasks/manifest_pass.json
```

`task-manifest` limits the gate to tasks compatible with the trajectory (see [`tasks/manifest_pass.json`](../tasks/manifest_pass.json)). Without it, all `tasks/*.json` are evaluated — fixture trajectories only pass a subset.

**Option B — external repo (after you publish or fork):**

```yaml
- uses: casualstack/agentbench-os/action@main
  with:
    tasks: .agentbench/tasks
    trajectory: .agentbench/last-run.json
```

**Option C — checkout + local action (works today without publishing):**

```yaml
- uses: actions/checkout@v4

- name: Checkout AgentBench OS
  uses: actions/checkout@v4
  with:
    repository: casualstack/agentbench-os
    path: agentbench-os

- uses: ./agentbench-os/action
  with:
    tasks: .agentbench/tasks
    trajectory: .agentbench/last-run.json
```

### 3. Add a trajectory

Commit a trajectory under `.agentbench/` (or point `trajectory:` at an existing path):

```
your-repo/
  .agentbench/
    last-run.json      # recorded agent session
    tasks/             # optional: repo-specific eval tasks
  .github/workflows/
    agentbench-gate.yml
```

Record trajectories from Cursor/Claude Code sessions (export tool calls → JSON). See the [72-hour plan](72_HOUR_PLAN.md) trajectory recorder task for tooling.

Minimal trajectory shape:

```json
{
  "metadata": { "agent": "cursor", "model": "claude-sonnet-4" },
  "steps": [
    { "type": "tool_call", "tool": "write_file", "args": { "path": "src/foo.py", "content": "..." } }
  ]
}
```

### 4. Open a PR

Push a branch and open a pull request. The gate job runs `agentbench gate` and fails with oracle messages when a regression is detected.

## Workflow inputs

The composite action (`action/action.yml`) accepts:

| Input | Default | Description |
|-------|---------|-------------|
| `tasks` | `tasks` | Directory of eval task JSON files |
| `trajectory` | *(required)* | Path to agent trajectory JSON |
| `task-manifest` | *(empty)* | Optional manifest JSON listing compatible `task_files` |
| `python-version` | `3.11` | Python version for the runner |

## Manual run

Use **workflow_dispatch** to re-run the gate with a different trajectory (both example workflows include this):

1. GitHub → Actions → **AgentBench Gate** → Run workflow
2. Set **trajectory** to e.g. `.agentbench/last-run.json`

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No task JSON files found` | Add `*.json` tasks under the `tasks` input path, or copy samples from AgentBench OS `tasks/` |
| `Trajectory file not found` | Ensure the path is committed and matches the workflow `trajectory` input |
| Gate passes locally, fails in CI | CI uses a fresh checkout — confirm trajectory paths are relative to repo root |
| `pip install -e .` fails | Consumer repos using Option C need AgentBench OS checked out; Option B needs a published package or git URL install step |

## Next steps

- Add repo-specific tasks under `.agentbench/tasks/` with oracles for files your agents must not touch
- Run the [model matrix](BENCHMARKS.md) to compare pass rates across models and prompts
- See [Oracle spec](ORACLE_SPEC.md) for available oracle types
