# Architecture

AgentBench OS evaluates **recorded agent trajectories** against **property-based oracles**. It is not a live agent runner or trace dashboard — it is a CI gate that answers: *did this agent run violate our constraints?*

## Data flow

```
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

### Eval DSL (`agentbench.dsl`)

Validates task and trajectory JSON before evaluation. Catches schema errors early (unknown oracle types, missing params).

### Models (`agentbench.models`)

- **EvalTask** — prompt, initial workspace files, oracle list
- **Oracle** — typed check with params
- **RunResult** — aggregate pass/fail + per-oracle messages

### Runner (`agentbench.runner`)

**AgentRunner** (MVP):

1. Materialize `task.workspace` into a temp directory
2. Replay `trajectory.file_edits()` onto that directory
3. Return final workspace path for oracle checks

Future: swap trajectory replay for live agent invocation (Cursor SDK, Claude Code API) while keeping the same oracle interface.

**Trajectory** parses tool-call steps and exposes:

- `file_edits()` — write/edit/str_replace operations
- `commands()` — shell invocations
- `find_network_violations()` — pattern scan for offline constraints

### Oracles (`agentbench.oracles`)

Pluggable checks registered via `@register_oracle`. Each oracle receives:

- Oracle config from task JSON
- Final workspace path
- Full trajectory (for behavioral checks)
- Initial workspace dict (for diff / protected-file checks)

All oracles must pass for `RunResult.passed == True`.

### Gate (`agentbench.gate`)

**Evaluator** wires runner + oracles. Supports single-task (`evaluate_files`) and directory batch (`evaluate_directory`) for CI.

### CLI (`agentbench.cli`)

- `agentbench run --task T --trajectory J` — single eval, exit 0/1
- `agentbench gate --tasks DIR --trajectory J` — batch gate
- `agentbench watch` — local session accountability monitoring
- `agentbench diff --baseline A --candidate B` — trajectory-to-trajectory diff report

### GitHub Action (`action/`)

Composite action: install package, run `agentbench gate`. Workflow stub at `.github/workflows/agentbench-gate.yml`.

### Client (`agentbench.ui`)

Local dashboard (desktop app and browser mode) over loopback-only JSON API:

- Live watch feed (`/api/watch`) for ongoing session guardrails
- Gate runner (`/api/gate`) for trajectory + task evaluation
- Trajectory explorer (`/api/trajectories`, `/api/trajectory`)
- Trajectory diff view (`/api/diff`)
- Matrix runner (`/api/matrix-configs`, `/api/matrix`)
- Run history (`/api/history`)
- JSONL recorder (`/api/record`)

## Design principles

1. **No API keys for MVP** — trajectories are pre-recorded JSON fixtures
2. **Oracle-first** — checks encode *properties* (tests pass, file untouched), not single golden outputs
3. **PR-native** — exit codes drive CI; human-readable summaries for logs
4. **Extensible registry** — new oracle = new class + `@register_oracle`

## Extension points

| Layer | Next step |
|-------|-----------|
| Runner | Live agent execution + trajectory recording |
| Oracles | `diff_max_lines`, `no_new_dependencies`, `coverage_min` |
| DSL | YAML tasks, oracle composition (`all_of` / `any_of`) |
| Gate | Statistical pass over N runs, flake detection |
| Action | Upload trajectory artifact from agent session |
