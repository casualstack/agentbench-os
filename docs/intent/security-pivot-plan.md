# AgentBench OS — Security & Accountability Pivot (approved build plan)

> Status: **Approved for build** by the Opus reviewer on 2026-07-15.
> This document is the authoritative brief for the build agent. Where the
> reviewer's rulings/amendments below conflict with the plan body, **the rulings win.**

## Founder decisions (hard constraints)

1. **Phased teeth.** Design both accountability (Phase 1) and enforcement
   (Phase 2), but build **Phase 1 first**. Phase 2 gets architecture + seams only,
   no build.
2. **Dual billing.** Security & accountability AND eval/benchmarking are
   **co-equal pillars** over a shared trajectory + oracle core. Nothing is
   deleted; it is restructured.
3. **Keep the name.** "AgentBench OS" stays — no package/CLI/repo/action rename.
   Only the tagline/positioning shifts: "pytest for AI coding agents" →
   "security & accountability for AI coding agents."

## Reviewer rulings (resolve the plan's open decisions — these are binding)

1. **Reorg = Option A (real physical submodule moves).** "Keep the name" fixes
   the top-level `agentbench` package / CLI / repo / action only; internal
   submodules may move. Do the real reorg into `core/ adapters/ accountability/
   eval/`.
2. **Audit store default = global `~/.agentbench/audit.db`**, with `--audit-db PATH`
   override honored on every audit/incident/watch verb.
3. **Phase 2 roadmap:** Claude Code is the single concrete real-time interception
   target (PreToolUse hook — verify exact schema at Phase 2 kickoff, not now).
   Codex / Cursor / Antigravity are documented as near-real-time accountability
   or config-authoring only; **real-time blocking is not confirmed for them and
   must not be promised.**
4. **Break internal import paths without back-compat shims** — 0.1.0 alpha, all
   callers updated in the same commit. Do not leave dead `agentbench.watch` /
   `agentbench.oracles` shims behind.

## Reviewer amendments (apply on top of the plan body)

- **A. No heartbeat rows in the hash-chained `events` table.** Only real
  accountability events (alerts) are appended to the chained store. Any
  `session_seen`/bookkeeping tracking, if kept at all, goes in a separate
  NON-chained table. Every chained row must be a genuine event.
- **B. The three reorg commits are pure moves.** Import updates + the single
  legitimate `core/steps.py` dedup only — no signature or logic changes except
  the documented `validate_trajectory_dict` relocation. If any test needs more
  than an import-path fix to stay green, STOP and report; do not change behavior
  to make a test pass.

## Build discipline (binding)

- Work on a new branch `pivot/security-accountability` cut from current HEAD
  (`feat/multi-client-watch`). Do NOT push. Do NOT open a PR unless asked.
- One commit per numbered task in §6. Run the FULL suite after every task; it must
  stay green (current baseline: 165 passing) before moving to the next task.
- **Commit messages must be indistinguishable from human-authored work:** no
  `Co-Authored-By`, no "Generated with Claude", no AI/robot footers, and **no
  model names or "an agent planned/built this" process narration** anywhere in
  commit messages or the shipped docs. (This overrides any default commit
  formatting.)
- **Runtime verification is mandatory**, not optional: actually run the flows in
  §7 (watch against a synthetic session, `audit verify`, the tamper proof, the
  regression demo) — typecheck/pytest-green alone does NOT count as verified.
- Execute tasks 1–11. Task 12 (UI surface) is optional: only if the suite stays
  green and there is time; skip cleanly otherwise.
- If you hit a genuine ambiguity not resolved by the rulings/amendments above,
  STOP and report it rather than guessing.

---

# Plan body (as authored by the planning agent)

## 1. Current-state map

**Already accountability-native (real, not aspirational):**
- `src/agentbench/watch/watcher.py` — `SessionWatcher`: polling tail (append-only JSONL) + re-parse-and-diff (SQLite) discovery loop, in-memory session state only.
- `src/agentbench/watch/rules.py` — 14 zero-config rules (`deleted_assertion`, `weakened_assertion`, `skipped_test`, `secret_file_write`, `hook_bypass`, `destructive_command`, `out_of_project_write`, `potential_secret_exposure`, etc.) → `Alert` dataclass. Pure regex, in-memory, fast, no I/O.
- `src/agentbench/watch/sources.py` + `watch/adapters/{base,claude_code,codex,cursor,antigravity}.py` — pluggable `SourceAdapter` registry. All four are observation-only; none can intercept or block. Cursor and Antigravity are best-effort/detect-only.
- `src/agentbench/watch/digest.py`, `watch/notify.py` — plain-English markdown digest, best-effort OS-native desktop notification (never raises).
- `src/agentbench/recorder.py` — normalizes arbitrary JSONL exports into the shared step vocabulary.
- `src/agentbench/diff_report.py` — trajectory-to-trajectory diff, git-like, markdown/JSON.
- CLI: `agentbench watch`, `agentbench diff` (`src/agentbench/cli/main.py`).
- Tests: `test_watch.py`, `test_codex_adapter.py`, `test_digest.py`, `test_notify.py`, `test_ui_watch.py`.
- `docs/intent/accessible-app.md` already frames this as "agent accountability."

**Eval/benchmark-only (keep as co-equal pillar):**
- `src/agentbench/oracles/{base,test_must_pass,file_not_modified,no_network,assertion_exists}.py` — registry pattern, 4 checks.
- `src/agentbench/gate/{evaluator,manifest}.py` — `Evaluator.evaluate_files/evaluate_directory`.
- `src/agentbench/runner/agent_runner.py` — `AgentRunner`: replays a trajectory into a temp workspace so oracles can inspect it post-hoc.
- `src/agentbench/dsl/validator.py` — task/oracle validation, but also `validate_trajectory_dict` (shared, not eval-only).
- `src/agentbench/benchmark/matrix.py` (real impl) + `src/agentbench/matrix.py` (re-export shim) — model×prompt pass-rate matrix, drift detection.
- `src/agentbench/models/task.py` — `EvalTask`, `Oracle`, `OracleResult`, `RunResult`.
- CLI: `agentbench run`, `agentbench gate`, `agentbench matrix`.
- `action/` + `.github/workflows/agentbench-gate.yml` — PR gate demo, calls `agentbench.gate.evaluator` from `action/entrypoint.py`.
- Tests: `test_evaluator.py`, `test_oracles.py`, `test_dsl.py`, `test_matrix.py`, `test_trajectory.py`.

**Genuinely shared core (used by both, not physically expressed as such):**
- `src/agentbench/runner/trajectory.py` — `Trajectory`/`TrajectoryStep`, consumed by oracles (via `AgentRunner`) and by `diff_report.py`/`recorder.py`.
- Concrete triplicated duplication: write/run tool-name sets defined in `runner/trajectory.py` (`write_tools`/`run_tools`, plus inline path/command key-precedence) and again in `watch/rules.py` (`_WRITE_TOOLS`/`_RUN_TOOLS`, `_step_path()`/`_step_command()`).
- `dsl/validator.py::validate_trajectory_dict` — called from `Trajectory.from_dict`; shared despite living in the eval-only `dsl` package.
- `watch/adapters/*` — session ingestion; meant to feed both pillars.
- `ui/server.py` and `cli/main.py` — both import across every module above; de facto integration point.

**Import-graph check:** `oracles/`, `gate/`, `runner/`, `dsl/`, `benchmark/`, `models/` have zero imports from `watch/`, and vice versa. Only `ui/server.py` and `cli/main.py` import both sides — the physical split is mechanical and non-circular.

**Not yet real (needs building):** no durable audit store (alerts live only in `SessionWatcher._sessions` + stdout), no tamper-evidence, no incident lifecycle, no Phase 2 seam types.

## 2. Target architecture

```
src/agentbench/
├── __init__.py
├── cli/
│   └── main.py                  # unchanged entrypoint; subcommands grouped by pillar in --help
├── core/                        # shared internals — new
│   ├── __init__.py
│   ├── steps.py                 # WRITE_TOOLS/RUN_TOOLS + step_path()/step_command() (dedup)
│   └── trajectory.py            # Trajectory, TrajectoryStep, normalize_rel_path, validate_trajectory_dict
├── adapters/                    # promoted from watch/adapters/ — shared ingestion
│   ├── __init__.py
│   ├── base.py
│   ├── claude_code.py
│   ├── codex.py
│   ├── cursor.py
│   └── antigravity.py
├── accountability/               # Pillar 1 — Phase 1 ships here
│   ├── __init__.py
│   ├── watcher.py                 # from watch/watcher.py
│   ├── rules.py                   # from watch/rules.py, imports core.steps
│   ├── sources.py                 # from watch/sources.py
│   ├── session_parser.py          # from watch/claude_code.py (renamed)
│   ├── digest.py
│   ├── notify.py
│   ├── recorder.py                # from top-level recorder.py
│   ├── diff.py                    # from diff_report.py
│   ├── audit/                     # NEW — see §3
│   │   ├── __init__.py
│   │   ├── store.py               # AuditStore (sqlite, WAL, append-only, hash-chained)
│   │   ├── chain.py               # compute_hash()/verify_chain() — isolated, unit-testable
│   │   └── incidents.py           # Incident + IncidentStore (mutable status, NOT chained)
│   └── policy/                    # NEW — Phase 2 seam only, see §4
│       ├── __init__.py
│       ├── decision.py            # Decision enum, PolicyContext, PolicyVerdict
│       └── engine.py              # PolicyEngine ABC, ObservePolicyEngine (Phase 1 default)
├── eval/                          # Pillar 2 — restructured, not rebuilt
│   ├── __init__.py
│   ├── models.py                  # from models/task.py
│   ├── dsl/
│   │   ├── __init__.py
│   │   └── validator.py           # task/oracle validation only
│   ├── oracles/                   # from oracles/*
│   │   ├── base.py
│   │   ├── test_must_pass.py
│   │   ├── file_not_modified.py
│   │   ├── no_network.py
│   │   └── assertion_exists.py
│   ├── gate/                      # from gate/*
│   │   ├── evaluator.py
│   │   └── manifest.py
│   ├── runner.py                  # from runner/agent_runner.py
│   └── matrix.py                  # from benchmark/matrix.py; delete old top-level matrix.py shim
└── ui/
    ├── app.py
    └── server.py                  # import paths updated; + /api/incidents, /api/audit/verify
```

**Public surface per pillar:**
- `agentbench.accountability` exports: `SessionWatcher`, `WatchEvent`, `Alert`, `check_steps`, `discover_sessions`, `render_digest`, `notify`, `AuditStore`, `Incident`, `PolicyEngine`, `Decision` (seam types always importable).
- `agentbench.eval` exports: `EvalTask`, `Oracle`, `RunResult`, `Evaluator`, `AgentRunner`, `MatrixRunner`, `MatrixConfig`.
- Both depend on `agentbench.core` and `agentbench.adapters`; neither depends on the other.

## 3. Phase 1 build plan (ships now)

### 3a. Elevate the accountability pillar (mechanical + dedup)
- Move `watch/*` → `accountability/*`, eval modules → `eval/*`, per §2. Update every importer (`cli/main.py`, `ui/server.py`, `action/entrypoint.py`, `scripts/*` if they import internals, all of `tests/`).
- Extract `core/steps.py` from the triplicated definitions; both `accountability/rules.py` and `core/trajectory.py` import from it.
- Move `validate_trajectory_dict` into `core/trajectory.py`; `eval/dsl/validator.py` keeps only task/oracle validation and re-imports `validate_trajectory_dict` for back-compat within the package.

### 3b. Durable, hash-chained audit trail — `accountability/audit/store.py` + `chain.py`
**Claim earned:** "AgentBench keeps a local, append-only record of every alert it raised, and can prove that record hasn't been silently edited since it was written." **Claim NOT earned:** proof the underlying agent session log itself wasn't edited; protection against a sophisticated local attacker with DB write access + knowledge of the scheme.
- SQLite (stdlib `sqlite3`, no new dependency). Default path `~/.agentbench/audit.db` (global — reviewer ruling 2). `--audit-db PATH` override on every new/changed verb. WAL mode, single-writer lock mirroring `ui/server.py`'s existing lock pattern.
- `events` table (append-only): `id`, `ts`, `agent`, `session_id`, `cwd`, `model`, `step_index`, `rule`, `severity`, `title`, `detail`, `path`, `source_path`, `source_size`, `source_mtime`, `record_hash`, `prev_hash`.
- Chain: `record_hash = sha256(prev_hash + canonical_json(row_fields_excluding_hash))`, `prev_hash="GENESIS"` for row 1. `chain.py::verify_chain(conn) -> int | None` walks rows in `id` order, returns first mismatched row id or `None`.
- `store.append(record) -> int` — single INSERT + hash compute, called from the poll loop via a thin adapter (keep `watcher.py` storage-agnostic).
- `agentbench watch` wiring: every alert is appended automatically. `--no-audit-log` opts out (default on). **Reviewer amendment A: no heartbeat/`session_seen` rows in the chained table.**

### 3c. Incident lifecycle — `accountability/audit/incidents.py`
**Claim earned:** "a queryable backlog with disposition, not just a scrolling terminal stream." **Not built (anti-gold-plating):** cross-alert dedup/grouping — ship 1:1 alert→incident, note grouping as future work.
- `incidents` table (separate, mutable, NOT part of the hash chain): `incident_id` (`sha256(session_id + step_index + rule)[:16]`), `event_id` FK, `status` (`open`/`acknowledged`/`resolved`, default `open`), `note`, `resolved_at`, `resolved_by`.
- CLI: `agentbench incidents list [--status ...] [--project PATH] [--severity ...] [--db PATH]`, `incidents show <id>`, `incidents ack <id> [--note]`, `incidents resolve <id> [--note]`.
- `agentbench audit verify [--db PATH]` — runs `verify_chain`, prints OK or first broken row, exit 0/1.
- `agentbench audit export --output FILE [--project] [--since ISO8601] [--format md|json]` — durable historical equivalent of `watch --digest`, reusing `digest.py` rendering + incident status.

### 3d. Repositioning cleanup (tagline + docs)
- `README.md`: H1 tagline → "Security & accountability for AI coding agents — with the eval/benchmark suite to prove your gates work." Reorder body so accountability/watch precedes the eval quickstart; present both as equally-weighted sections.
- `pyproject.toml` `description` → dual-pillar phrasing.
- `cli/main.py::build_parser()` description → dual-pillar; reorder subparsers so `--help` groups accountability verbs (`watch`, `diff`, `incidents`, `audit`) before eval verbs (`run`, `gate`, `matrix`), `ui`/`app` last.
- `docs/ARCHITECTURE.md`: rewrite opening to describe both pillars over shared `core`/`adapters`; replace data-flow diagram with parallel accountability/eval paths.
- `docs/WATCH.md`: add "Audit trail" and "Incidents" sections (`audit verify`/`audit export`/`incidents *`).
- New `docs/ACCOUNTABILITY.md`: pillar overview + a **"Phase 2 (roadmap): enforcement"** section stating plainly what is designed-but-not-built, and the tamper-evidence scope limits (§5).
- `docs/ORACLE_SPEC.md` / `docs/EVAL_DSL.md`: one-line pillar-scope header; update "Adding a new oracle" for the new `eval/gate/evaluator.py` import path.
- `docs/manual/Welcome.md`: reframe opening + "Three core ideas" to lead with accountability/watch as idea #1, property oracles as idea #2.
- Leave untouched (internal-only): `HANDOFF_TO_CLAUDE.md`, `docs/72_HOUR_PLAN.md`, `docs/STARTUP_PLAN.md`, `docs/GITHUB_ORG_RUNBOOK.md`, `docs/GITHUB_SETUP.md`, `docs/DOMAIN_SETUP.md`, `docs/COMPETITIVE_LANGCHAIN.md`.
- `action/action.yml` description accurate for the eval gate; leave as-is (optional one-line note that `agentbench watch` provides the accountability pillar).

### 3e. Tests per new capability
- `tests/test_audit_chain.py` — pure `compute_hash`/`verify_chain` over dict rows.
- `tests/test_audit_store.py` — append/read round trip; `verify_chain()` OK on untouched store; direct `UPDATE`/`DELETE` a row via raw `sqlite3` and assert `verify_chain()` catches it at the right id.
- `tests/test_incidents.py` — 1:1 alert→incident creation, status transitions, `--status` filter, stable `incident_id` across two runs.
- `tests/test_cli.py` additions — `audit verify`/`audit export`/`incidents *` argparse wiring + exit codes (subprocess style).
- `tests/test_policy_seams.py` — `Decision`/`PolicyContext`/`PolicyVerdict`/`PolicyEngine` import + construct; `ObservePolicyEngine.evaluate()` always returns `ALLOW`; regression assertion that wiring it into `SessionWatcher` changes zero observable behavior.
- Mechanically update every moved test's imports; unchanged assertions are the acceptance bar for the reorg commits.

## 4. Phase 2 design + seams (design only — build only the seam types)

### Policy model
```python
# accountability/policy/decision.py
class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"

@dataclass
class PolicyContext:
    agent: str
    session_id: str
    cwd: str | None
    step: dict[str, Any]        # same normalized {"tool":..., "args":...} shape rules.check_step consumes
    step_index: int
    alerts: list[Alert]

@dataclass
class PolicyVerdict:
    decision: Decision
    reason: str
    rule: str | None = None
```
```python
# accountability/policy/engine.py
class PolicyEngine(ABC):
    @abstractmethod
    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict: ...

class ObservePolicyEngine(PolicyEngine):
    """Phase 1 default. Always ALLOW — accountability only, no enforcement."""
    def evaluate(self, ctx: PolicyContext) -> PolicyVerdict:
        return PolicyVerdict(Decision.ALLOW, reason="phase1: observe-only")
```
Phase 2's real engine (not built now) reads `.agentbench/policy.yml` (per-rule decision overrides, protected-path DENY list, approver + fail-open/closed timeout) and returns real verdicts. Design target mapping: `critical` → `REQUIRE_APPROVAL` (configurable to `DENY`), `warning` → `ALLOW` + notify.

### Per-client interception reality-check
| Client | Phase 1 today | Phase 2 real-time interception? |
|---|---|---|
| Claude Code | tails `~/.claude/projects/*/*.jsonl` post-write | **Plausible** via PreToolUse hook returning allow/deny/ask → a new `ClaudeCodeHookAdapter`. Verify exact hook schema/latency at Phase 2 kickoff. |
| Codex CLI | tails `~/.codex/sessions/.../rollout-*.jsonl` post-hoc | **Unconfirmed** — has built-in approval modes but no confirmed third-party pre-exec hook. Needs verification before scoping; do not promise. |
| Cursor | re-parses `state.vscdb` per poll | **Not external interception.** Best case: write Cursor's own allow/deny config (config authoring, not enforcement). |
| Antigravity | detect-only | No interception story yet. |

**Conclusion:** real-time ALLOW/DENY/REQUIRE-APPROVAL is credibly buildable for Claude Code only near-term. Interception capability is per-adapter, opt-in, defaults false everywhere.

### Exact seams Phase 1 must expose now
1. `SourceAdapter.supports_interception: bool = False` on `adapters/base.py`, default False on all four adapters.
2. Preserve `rules.check_step(step: dict, step_index: int, *, cwd: str | None)`'s transport-agnostic dict shape verbatim (locked by a regression test, not new code).
3. Keep `PolicyEngine.evaluate()` synchronous + side-effect-free (regex/in-memory only — no file/network I/O) for a tight hook latency budget.
4. `AuditStore.append()` stays cheap/WAL/single-INSERT so a future hook adapter can call it fire-and-forget without redesign — never on the decision hot path.
5. `REQUIRE_APPROVAL` for Claude Code delegates to the client's own "ask" UX (hook returns `"ask"`) — no AgentBench approval UI needed. Documentation note only.

## 5. Risks & honest reality-checks

- **"Tamper-evident" scope discipline is the top embarrassment risk.** The hash chain proves AgentBench's own local `audit.db` wasn't silently edited after write. It proves nothing about the underlying session log being scrubbed before AgentBench read it. Docs/marketing must say "tamper-evident audit trail of what AgentBench observed and recorded" — never "proof the agent's actions weren't hidden." State this explicitly in `docs/ACCOUNTABILITY.md`.
- **Hash chain ≠ crypto security vs. a determined local attacker.** Plain SHA-256 chaining (no HMAC key, no external anchor) detects accidental corruption and naive edits, not an attacker who recomputes the whole chain. Do NOT build HMAC-with-keychain in Phase 1 (real cross-platform cost, doesn't close the gap for a single-dev-machine threat model). State the limitation in docs.
- **Observation-only is the whole Phase 1 shape.** All adapters read logs after the client wrote them. Any copy implying real-time protection before Phase 2 is false advertising.
- **Cursor schema is reverse-engineered/undocumented** — keep "best-effort" qualifier; don't upgrade the claim just because "security" sounds stronger than "eval."
- **Codex CLI hook capability is asserted, not verified** — don't scope Phase 2 effort against it until confirmed.
- **Don't let "incidents" become a bug tracker** — 1:1 alert→incident, 3-state status, note field; no assignment/SLA/grouping in Phase 1.
- **Reorg touches ~25+ files** — mitigated by isolated pure-move commits, zero-behavior-change bar, full suite green, confirmed no circular imports.

## 6. Sequenced task list for the build agent

Each task = one commit-sized unit. Run `pytest -q` after every task; must stay green before moving on.

1. **Reorg: `core/` + `adapters/` extraction.** Create `core/steps.py` (dedup), move `runner/trajectory.py` → `core/trajectory.py` (incl. `validate_trajectory_dict`), move `watch/adapters/*` → `adapters/*`. Update importers. Verify: suite green, `python -m agentbench.cli.main watch --once` runs.
2. **Reorg: promote `accountability/`.** Move `watch/{watcher,rules,sources,digest,notify}.py` → `accountability/`, `watch/claude_code.py` → `accountability/session_parser.py`, `recorder.py`/`diff_report.py` → `accountability/{recorder,diff}.py`. Update `cli/main.py`, `ui/server.py`. Verify: suite green; `agentbench diff` still produces expected markdown.
3. **Reorg: promote `eval/`.** Move `models/task.py` → `eval/models.py`, `oracles/*` → `eval/oracles/*`, `gate/*` → `eval/gate/*`, `runner/agent_runner.py` → `eval/runner.py`, `benchmark/matrix.py` → `eval/matrix.py`; delete top-level `matrix.py` shim + `benchmark/` package. Update `action/entrypoint.py`, `cli/main.py`, `ui/server.py`, `scripts/*`. Verify: suite green; `agentbench run` task 01 PASS on pass fixture, FAIL on regression fixture.
4. **`accountability/audit/chain.py`.** `compute_hash()`/`verify_chain()` pure over dict rows — no SQLite. Test: `tests/test_audit_chain.py`.
5. **`accountability/audit/store.py`.** `AuditStore` (SQLite, WAL, `append()`, `iter_events()`, filters). Test: `tests/test_audit_store.py` incl. direct-row-mutation tamper detection.
6. **Wire `AuditStore` into `agentbench watch`.** `--audit-db` / `--no-audit-log` flags; poll loop appends alerts via a thin adapter (no SQLite inside `watcher.py`). New verb `agentbench audit verify`. Verify: run `watch --once` twice against a fixture home, `audit verify` OK, then corrupt a row → reports broken id, exit 1.
7. **`accountability/audit/incidents.py` + CLI.** `Incident`/`IncidentStore`, `incidents list|show|ack|resolve`. Test: `tests/test_incidents.py`.
8. **`agentbench audit export`.** Reuse `digest.py` rendering against the persisted store; `--format md|json`, `--since`, `--project`. Test: `tests/test_audit_export.py`.
9. **`accountability/policy/{decision,engine}.py`.** Seam types + `ObservePolicyEngine`, wired into `SessionWatcher` as a no-op pass-through (result discarded/logged, not acted on). Test: `tests/test_policy_seams.py`.
10. **`SourceAdapter.supports_interception` flag** on `adapters/base.py`, default False on all four. Test: extend `tests/test_watch.py`.
11. **Docs/repositioning pass** (§3d). No code changes; grep docs for stale `agentbench.watch`/`agentbench.oracles` import paths post-reorg.
12. **(Optional) UI surface for incidents/audit** — `/api/incidents`, `/api/audit/verify` in `ui/server.py`. Test: extend `tests/test_ui.py`/`test_ui_watch.py`. Skip cleanly if time/green-suite doesn't allow.

## 7. Verification strategy (must actually run — not just pytest)

1. Full suite before/after every task: `& ".venv\Scripts\python.exe" -m pytest -q` — stays at 165 + new tests, never fewer.
2. Regression demo post-reorg: `agentbench run` task 01 on pass fixture → PASS, on regression fixture → FAIL; `agentbench gate` → exit 0.
3. Watch end-to-end vs synthetic home: write a fake `~/.claude/projects/<slug>/<id>.jsonl` with a tool_use that deletes a test assertion; `agentbench watch --once --audit-db build\audit-smoke.db`; confirm critical alert + `audit verify` OK.
4. Tamper proof: `UPDATE events SET detail='edited' WHERE id=1;` via `sqlite3`, re-run `audit verify` → broken chain at row 1, exit 1. Script this, don't eyeball once.
5. Incidents round trip: `incidents list --status open` shows the alert; `incidents ack <id> --note "reviewed"` then `incidents show <id>` → acknowledged; `audit verify` still passes (proves status mutation doesn't touch chained `events`).
6. Eval pillar behavior-freeze: `agentbench diff ...` and `agentbench matrix ...` produce identical output to pre-pivot.
7. Action smoke locally: `python action\entrypoint.py --tasks tasks --trajectory tests\fixtures\trajectory_pass.json --report build\report.json` — confirms updated import path resolves.
8. UI smoke: `agentbench ui --no-browser`, hit `/api/watch` and (if task 12) `/api/incidents`, `/api/audit/verify`.
9. Windows notification path: one live `agentbench watch` alert to confirm the PowerShell toast fallback in `notify.py` still fires post-reorg.
