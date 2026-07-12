# AgentBench OS

By **[Casualstack](https://casualstack.dev)** — execution accountability for AI agents.

**Continuous agent reliability CI** — property-based oracles that gate AI coding agent runs on pull requests.
AgentBench is pytest for agent trajectories: load a task, replay a recorded agent run, and fail the gate when oracles detect regressions (deleted assertions, scope creep, network access, failing tests).

## Quickstart

```bash
# Install (Python 3.11+)
cd agentbench-os
pip install -e ".[dev]"

# Run a single eval
agentbench run \
  --task tasks/01_fix_failing_test_no_delete.json \
  --trajectory tests/fixtures/trajectory_pass.json
# → [PASS]

agentbench run \
  --task tasks/01_fix_failing_test_no_delete.json \
  --trajectory tests/fixtures/trajectory_regression.json
# → [FAIL] (assertion deleted / test file modified)

# CI gate over all tasks
agentbench gate --tasks tasks/ --trajectory tests/fixtures/trajectory_pass.json

# Git-like accountability diff between trajectories
agentbench diff \
  --baseline tests/fixtures/trajectory_pass.json \
  --candidate tests/fixtures/trajectory_regression.json \
  --output build/diff-report.md

# Desktop client (native window): gate runner + task browser + recorder
# Prebuilt Windows/macOS/Linux downloads: see docs/UI.md
# (Windows/macOS may warn the build is from an unidentified publisher —
#  see docs/UI.md#windows-says-it-protected-your-pc)
pip install -e ".[app]"
agentbench app

# Same client in a browser tab
agentbench ui

# Local watch mode for accountability alerts
agentbench watch --once

# Run tests
pytest -q
```

## Oracle types

| Type | What it checks |
|------|----------------|
| `test_must_pass` | Shell command (usually pytest) exits 0 |
| `file_not_modified` | Agent did not change a protected file |
| `no_network` | Trajectory has no curl/HTTP/pip network patterns |
| `assertion_exists` | Regex pattern still present in a file |

See [docs/ORACLE_SPEC.md](docs/ORACLE_SPEC.md) and [docs/EVAL_DSL.md](docs/EVAL_DSL.md).

## Watch mode — zero-config, multi-client

Point AgentBench at the AI coding sessions already on your machine — no task
JSON, no trajectory exports. It discovers sessions through a pluggable
**source adapter** per client, checks them against plain-English rules, and
keeps watching live.

```bash
agentbench watch                        # check history, then watch live
agentbench watch --once --digest report.md   # one-shot report you can share
```

| Client | Status |
|--------|--------|
| Claude Code | First-class (live tail) |
| Codex CLI | First-class (live tail) |
| Cursor | Parsed, best-effort (SQLite store) |
| Antigravity | Detected — parsing coming |

Rules catch the ways agents cut corners: deleted **or weakened** assertions
(`assert True`), disabled tests, out-of-project writes, secret-file writes
(`.env`, `*.pem`, …), git-hook bypass (`--no-verify`), destructive commands,
and unexpected network calls. New alerts raise a batched desktop notification
(optional; `agentbench[notify]`) and everything stays on your machine.

Adding a client is one `SourceAdapter` subclass. Full details: **[docs/WATCH.md](docs/WATCH.md)**.

## Add to your repo

Gate agent PRs in ~5 minutes. Full walkthrough: **[docs/GITHUB_ACTION.md](docs/GITHUB_ACTION.md)**.

**1. Copy a workflow template** (or use the setup script):

```bash
./scripts/dogfood_setup.sh /path/to/your-repo python
# Windows: .\scripts\dogfood_setup.ps1 -TargetRepo C:\path\to\your-repo
```

Templates: [`examples/dogfood/generic-python-repo-workflow.yml`](examples/dogfood/generic-python-repo-workflow.yml) · [`examples/dogfood/infra-k8s-workflow.yml`](examples/dogfood/infra-k8s-workflow.yml)

**2. Commit a trajectory** under `.agentbench/last-run.json` (recorded agent tool calls).

**3. Open a PR** — the gate runs `agentbench gate` and fails on oracle violations.

```yaml
- uses: casualstack/agentbench-os/action@main   # or ./action when vendoring
  with:
    tasks: .agentbench/tasks
    trajectory: .agentbench/last-run.json
```

This repo also ships `.github/workflows/ci.yml` (pytest) and `.github/workflows/agentbench-gate.yml` (self-gate demo).

## Benchmarks

Compare pass rates across models and prompts with the matrix runner. See **[docs/BENCHMARKS.md](docs/BENCHMARKS.md)**.

```bash
./scripts/run_matrix.sh          # Linux / macOS
.\scripts\run_matrix.ps1         # Windows
```

Reference run of the `fixture-2x2` matrix (recorded trajectories replayed against the 6-task subset — a clean fix vs. an agent that deletes the failing assertion):

| Trajectory | Prompt | Pass rate |
|------------|--------|-----------|
| clean fix (`trajectory_pass`) | direct | 6/6 (100%) |
| clean fix (`trajectory_pass`) | verbose | 6/6 (100%) |
| assertion-delete regression (`trajectory_regression`) | direct | 1/6 (16.7%) |
| assertion-delete regression (`trajectory_regression`) | verbose | 1/6 (16.7%) |

Overall pass rate 58.3%, zero drift against baseline (threshold 5%). See [BENCHMARKS.md](docs/BENCHMARKS.md) for schema and how to add live model runs.

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Eval DSL](docs/EVAL_DSL.md)
- [Oracle spec](docs/ORACLE_SPEC.md)
- [GitHub Action setup](docs/GITHUB_ACTION.md)
- [Watch mode: multi-client adapters + accountability guards](docs/WATCH.md)
- [Dashboard / UI client](docs/UI.md)
- [Benchmarks](docs/BENCHMARKS.md)

## License

MIT
