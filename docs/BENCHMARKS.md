# Benchmarks — model × prompt matrix

AgentBench compares **pass rates** across models and prompt variants by running the same eval tasks against different recorded trajectories. Use this to spot score drift when you change models, prompts, or agent tooling.

## Run the matrix

```bash
# From repo root (Linux / macOS)
./scripts/run_matrix.sh

# Windows
.\scripts\run_matrix.ps1

# Direct CLI (canonical YAML config with drift baseline)
python -m agentbench.cli.main matrix --config benchmarks/matrix.yaml --tasks tasks/

# Junior JSON config (2×2 claude/gpt labels, same task subset)
python -m agentbench.cli.main matrix --config configs/matrix.json --tasks tasks/ --output markdown
```

Default scripts use [`configs/matrix.json`](../configs/matrix.json). Canonical schema with drift baseline: [`benchmarks/matrix.yaml`](../benchmarks/matrix.yaml).

**Task subset:** Fixture trajectories only replay the `src/calc.py` fix recorded for task 01. Use [`benchmarks/task_subset_pass.json`](../benchmarks/task_subset_pass.json) (6 tasks) or pass `task_subset` / `task_files` in matrix config. Running against all 11 tasks without per-task trajectories inflates failure counts.

## Matrix config format

YAML (`benchmarks/matrix.yaml`) or JSON (`configs/matrix.json`):

```yaml
name: fixture-2x2
tasks_dir: tasks
task_subset: benchmarks/task_subset_pass.json
drift_threshold: 0.05
baseline:
  overall_pass_rate: 0.583
cells:
  - model: stub-pass
    prompt: direct
    trajectory: tests/fixtures/trajectory_pass.json
```

JSON uses `runs` as an alias for `cells`. See [`configs/matrix.json`](../configs/matrix.json) for the 2×2 claude/gpt example cross-referenced to the same `task_subset`.

| Field | Description |
|-------|-------------|
| `cells[]` / `runs[]` | Model/prompt label + trajectory path per matrix cell |
| `task_subset` | Manifest JSON with `task_files` compatible with fixture trajectories |
| `task_files` | Inline list of task JSON filenames (alternative to `task_subset`) |
| `baseline` | Expected pass rates for drift detection (YAML config) |
| `drift_threshold` | Flag when pass rate delta exceeds this fraction vs baseline |

## Expected output format

The matrix runner produces a **pass rate table** (markdown with `--output markdown`):

| Model | Prompt | Pass rate |
|-------|--------|-----------|
| stub-pass | direct | 100.0% |
| stub-regression | direct | 16.7% |

**Drift warnings** compare current run to `baseline` in YAML config:

```
Score drift detected (threshold=5.0%):
  cell stub-regression/direct: 0.0% -> 16.7% (delta +16.7%)
```

## Measured results (2026-07-05)

Commands run from repo root with `pip install -e ".[dev]"`.

### `benchmarks/matrix.yaml` — 6-task pass subset, stub model labels

```
python -m agentbench.cli.main matrix --config benchmarks/matrix.yaml --tasks tasks/
```

| Model | Prompt | Passed | Total | Pass rate |
|-------|--------|--------|-------|-----------|
| stub-pass | direct | 6 | 6 | 100% |
| stub-pass | verbose | 6 | 6 | 100% |
| stub-regression | direct | 1 | 6 | 16.7% |
| stub-regression | verbose | 1 | 6 | 16.7% |

Overall pass rate: **58.3%**. Baseline-aligned run reports no drift at 5% threshold.

### `configs/matrix.json` — same subset, claude/gpt labels

```
python -m agentbench.cli.main matrix --config configs/matrix.json --tasks tasks/ --output markdown
```

| Model | Prompt | Passed | Total | Pass rate |
|-------|--------|--------|-------|-----------|
| claude-sonnet | default | 6 | 6 | 100% |
| claude-sonnet | strict | 1 | 6 | 16.7% |
| gpt-4 | default | 6 | 6 | 100% |
| gpt-4 | strict | 1 | 6 | 16.7% |

### Full `tasks/` without subset (reference — not recommended for fixtures)

| Model | Prompt | Passed | Total | Pass rate |
|-------|--------|--------|-------|-----------|
| claude-sonnet | default | 6 | 11 | 54.5% |
| claude-sonnet | strict | 2 | 11 | 18.2% |

`trajectory_pass.json` passes **6/11** tasks when run against the full directory via `agentbench gate`; use `tasks/manifest_pass.json` or `--manifest` to scope the gate.

## Interpreting results

1. **Regression caught** — `trajectory_regression.json` fails assertion-integrity tasks; only `offline-fix-no-network` passes in the pass subset because it does not check assertions.
2. **Score drift** — re-run the matrix after agent IDE updates; drift >15% on the same trajectories warrants investigation.
3. **Flakes** — MVP uses single replay; future versions support N-run statistical gates (see [72-hour plan](72_HOUR_PLAN.md)).

## Related

- [GitHub Action setup](GITHUB_ACTION.md) — gate PRs with one trajectory + task manifest
- [Oracle spec](ORACLE_SPEC.md) — what each eval checks
- [Architecture](ARCHITECTURE.md) — evaluator and runner design
