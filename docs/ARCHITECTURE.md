# Architecture

AgentBench OS has two co-equal pillars over a shared trajectory + oracle
core: **accountability** (watch AI coding agents on this machine, keep a
tamper-evident record of what they did) and **eval/benchmarking**
(replay a recorded agent run against property-based oracles and fail the
gate on regressions). Nothing was deleted to build accountability — the
eval engine that shipped first is restructured underneath, not replaced.

```
src/agentbench/
├── core/            # shared: Trajectory, TrajectoryStep, tool-name vocabulary
├── adapters/         # shared: pluggable per-client session ingestion
├── accountability/    # pillar 1 — watch, audit trail, incidents, policy seam
├── eval/               # pillar 2 — oracles, gate, matrix (restructured, not rebuilt)
├── cli/                  # single entrypoint, subcommands grouped by pillar in --help
└── ui/                    # local dashboard over both pillars
```

Both pillars depend on `core` and `adapters`; neither pillar depends on
the other. `core` holds the trajectory step vocabulary
(`Trajectory`/`TrajectoryStep`, the write/run tool-name sets) that both
sides need to agree on without importing from each other. `adapters`
holds the per-client session ingestion (Claude Code, Cursor, Codex CLI,
Antigravity) that both pillars consume the same way.

## Data flow

Two parallel paths share the same normalized step vocabulary
(`write_file`/`str_replace`/`run_command`, produced by `core`/`adapters`)
but never share state:

```
Accountability (live, observation-only)
┌──────────────┐   ┌───────────────┐   ┌────────────┐   ┌───────────────┐
│ Session logs │──▶│ SourceAdapter │──▶│ SessionWatcher│─▶│  Alert/rules  │
│ (on disk)    │   │  (adapters/)  │   │ (accountability)│ │ (accountability)│
└──────────────┘   └───────────────┘   └────────────┘   └───────┬───────┘
                                                                  ▼
                                                   ┌───────────────────────┐
                                                   │  AuditStore (chained)  │
                                                   │  + IncidentStore        │
                                                   └───────────────────────┘

Eval (on demand, replay-based)
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Task JSON  │────▶│   AgentRunner    │────▶│ Temp workspace  │
│ (eval DSL)  │     │ setup + replay   │     │ (post-agent)    │
└─────────────┘     └────────▲─────────┘     └────────┬────────┘
                             │                        │
┌─────────────┐              │                        ▼
│ Trajectory  │──────────────┘               ┌─────────────────┐
│ JSON        │                              │    Evaluator    │
└─────────────┘                              │  run oracles    │
                                             └────────┬────────┘
                                                      ▼
                                             ┌─────────────────┐
                                             │   RunResult     │
                                             │ PASS / FAIL     │
                                             └─────────────────┘
```

## Components

### Core (`agentbench.core`)

Shared internals, not owned by either pillar:

- **Trajectory / TrajectoryStep** (`core.trajectory`) — parses tool-call
  steps and exposes `file_edits()`, `commands()`,
  `find_network_violations()`. Consumed by eval oracles via `AgentRunner`
  and by accountability's `diff`/`recorder`.
- **`WRITE_TOOLS` / `RUN_TOOLS` + `step_path()` / `step_command()`**
  (`core.steps`) — the tool-name vocabulary and args key-precedence both
  pillars need to agree on (`accountability.rules` and `core.trajectory`
  both import from here instead of each keeping its own copy).
- **`validate_trajectory_dict`** — lives here (not in the eval-only DSL
  package) because trajectory validation is shared, not eval-specific;
  `eval.dsl.validator` re-imports it for callers reaching through the
  eval package.

### Adapters (`agentbench.adapters`)

Pluggable per-client session ingestion, promoted out of the
accountability package so eval could depend on it too if it ever needs
to. One `SourceAdapter` subclass per client (Claude Code, Cursor, Codex
CLI, Antigravity), registered in `adapters.ADAPTERS`. Each adapter knows
whether its client is present (`detect`), where sessions live
(`discover`), and how to turn one session into the normalized step
vocabulary (`parse_session`). `supports_tail` says whether sessions are
append-only JSONL safe to byte-tail vs. needing a full re-parse each
poll; `supports_interception` is a Phase 2 seam (default `False`
everywhere in Phase 1 — see [ACCOUNTABILITY.md](ACCOUNTABILITY.md)).

### Accountability (`agentbench.accountability`)

- **SessionWatcher** (`accountability.watcher`) — discovers sessions via
  `adapters`, incrementally evaluates new steps, returns `WatchEvent`s.
  Storage-agnostic by design: it knows nothing about SQLite or the audit
  trail.
- **Rules** (`accountability.rules`) — 14 zero-config regex/in-memory
  checks over normalized steps, producing `Alert`s.
- **AuditStore / IncidentStore** (`accountability.audit`) — durable,
  hash-chained event log plus a mutable incident backlog on top of it.
  See [ACCOUNTABILITY.md](ACCOUNTABILITY.md) for the tamper-evidence
  scope (what it does and doesn't prove).
- **Policy seam** (`accountability.policy`) — `Decision`/`PolicyContext`/
  `PolicyVerdict`/`PolicyEngine` types for Phase 2; `ObservePolicyEngine`
  is the only Phase 1 implementation and always `ALLOW`s.
- **Digest / notify** — plain-English markdown reports and best-effort
  OS-native desktop notifications.

### Eval (`agentbench.eval`)

Restructured from the original top-level `dsl`/`models`/`oracles`/`gate`/
`runner`/`benchmark` packages into one `eval/` package — same behavior,
new location:

- **`eval.dsl`** — task/oracle JSON validation (trajectory validation
  moved to `core`, see above).
- **`eval.models`** — `EvalTask`, `Oracle`, `RunResult`.
- **`eval.oracles`** — pluggable checks registered via `@register_oracle`.
  Each oracle receives the oracle config, final workspace path, full
  trajectory, and the initial workspace dict. All oracles must pass for
  `RunResult.passed == True`.
- **`eval.runner`** — `AgentRunner` (MVP): materializes `task.workspace`
  into a temp directory, replays `trajectory.file_edits()` onto it,
  returns the final workspace path for oracle checks. Future: swap
  trajectory replay for live agent invocation while keeping the same
  oracle interface.
- **`eval.gate`** — `Evaluator` wires runner + oracles; single-task
  (`evaluate_files`) and directory batch (`evaluate_directory`) for CI.
- **`eval.matrix`** — model × prompt benchmark runner and score drift
  detection.

### CLI (`agentbench.cli`)

Single entrypoint; `--help` groups accountability verbs first, eval verbs
second, dashboard last:

- `agentbench watch` / `diff` / `incidents` / `audit` — accountability
- `agentbench run` / `gate` / `matrix` — eval
- `agentbench ui` / `app` — dashboard over both pillars

### GitHub Action (`action/`)

Composite action for the eval gate: install package, run `agentbench
gate`. Workflow stub at `.github/workflows/agentbench-gate.yml`. (The
accountability pillar's CI story is `agentbench audit verify` in a
pipeline step, not this action.)

### Client (`agentbench.ui`)

Local dashboard (desktop app and browser mode) over loopback-only JSON
API, covering both pillars:

- Live watch feed (`/api/watch`) for ongoing session guardrails
- Gate runner (`/api/gate`) for trajectory + task evaluation
- Trajectory explorer (`/api/trajectories`, `/api/trajectory`)
- Trajectory diff view (`/api/diff`)
- Matrix runner (`/api/matrix-configs`, `/api/matrix`)
- Run history (`/api/history`)
- JSONL recorder (`/api/record`)

## Design principles

1. **Accountability and eval are co-equal, not eval-plus-a-feature** —
   shared core, independent pillars, neither imports the other.
2. **No API keys for the eval MVP** — trajectories are pre-recorded JSON
   fixtures.
3. **Oracle-first** — eval checks encode *properties* (tests pass, file
   untouched), not single golden outputs.
4. **Zero-config accountability** — watch mode needs no task JSON, no
   setup; the 14 default rules apply out of the box.
5. **Observation before enforcement** — Phase 1 ships accountability
   only; the policy/interception seams exist so Phase 2 doesn't require
   re-touching call sites, but nothing blocks an agent's action yet.
6. **PR-native** — exit codes drive CI; human-readable summaries for
   logs, on both pillars.
7. **Extensible registries** — new oracle = new class + `@register_oracle`;
   new watched client = new `SourceAdapter` subclass.

## Extension points

| Layer | Next step |
|-------|-----------|
| Accountability | Real Phase 2 `PolicyEngine` reading `.agentbench/policy.yml`; Claude Code `PreToolUse` hook adapter |
| Eval runner | Live agent execution + trajectory recording |
| Oracles | `diff_max_lines`, `no_new_dependencies`, `coverage_min` |
| DSL | YAML tasks, oracle composition (`all_of` / `any_of`) |
| Gate | Statistical pass over N runs, flake detection |
| Action | Upload trajectory artifact from agent session |
