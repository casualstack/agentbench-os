# Accountability

AgentBench OS has two co-equal pillars over a shared trajectory + oracle
core: **accountability** (this doc) and **eval/benchmarking**
([ARCHITECTURE.md](ARCHITECTURE.md), [EVAL_DSL.md](EVAL_DSL.md),
[ORACLE_SPEC.md](ORACLE_SPEC.md)). Accountability answers a different
question than eval does: not "did this recorded run pass the gate?" but
"what did the AI coding agents already on this machine actually do, and
can I prove the record of that hasn't been quietly edited?"

## What ships today (Phase 1)

- **Zero-config session watching** (`agentbench watch`) — auto-detects
  Claude Code, Cursor, and Codex CLI sessions on this machine (Antigravity
  is detected only), tails them live, and raises plain-English alerts
  against 14 zero-config rules (deleted/weakened assertions, secret-file
  writes, destructive commands, hook bypasses, ...). See
  [WATCH.md](WATCH.md).
- **Durable, hash-chained audit trail** (`agentbench audit verify` /
  `audit export`) — every alert `watch` raises is appended to a local
  SQLite store, chained by hash so `audit verify` can prove the stored
  history hasn't been silently edited since it was written.
- **Incident backlog** (`agentbench incidents list|show|ack|resolve`) — a
  queryable backlog with disposition (open/acknowledged/resolved) layered
  on top of the audit trail, not just a scrolling terminal stream. 1:1
  alert-to-incident by design; cross-alert dedup/grouping is future work,
  not built here.
- **Policy seam types** (`agentbench.accountability.policy`) —
  `Decision`/`PolicyContext`/`PolicyVerdict`/`PolicyEngine` exist so Phase
  2 can slot a real engine in later without touching call sites again.
  The only engine Phase 1 ships, `ObservePolicyEngine`, always ALLOWs; its
  verdict is computed per step and discarded, never acted on.

## What "tamper-evident" means here (read this before you say it to anyone)

**Claim earned:** AgentBench keeps a local, append-only record of every
alert it raised, and can prove that record hasn't been silently edited
since it was written. Each row's `record_hash` commits to its own content
plus the previous row's hash (plain SHA-256 chaining, no new dependency);
`agentbench audit verify` walks the chain and reports the first row where
the stored hash no longer matches what gets recomputed.

**Claim NOT earned — say this out loud before you say "tamper-evident":**

- **This proves nothing about the underlying agent session log itself.**
  The hash chain covers AgentBench's own `audit.db`, written *after*
  AgentBench read a session log. If that session log was scrubbed or
  edited *before* AgentBench ever saw it, the chain has no way to know —
  it only proves the record of what AgentBench observed wasn't edited
  after the fact. Never say "proof the agent's actions weren't hidden";
  say "tamper-evident audit trail of what AgentBench observed and
  recorded."
- **This is not cryptographic security against a determined local
  attacker.** Plain SHA-256 chaining with no HMAC key and no external
  anchor detects accidental corruption and naive edits (an `UPDATE`
  statement, a stray text editor save) — it does not detect an attacker
  who edits a row and then recomputes every hash after it to match. That
  attacker needs local write access to `audit.db` *and* to understand the
  chain scheme, which is a real bar for casual tampering but not a
  cryptographic one. HMAC-with-keychain was considered and deliberately
  not built in Phase 1: real cross-platform cost, and it doesn't close
  the gap for the actual threat model here (a single developer's own
  machine), so it would be security theater relative to the effort.
- **Observation-only is the whole shape of Phase 1.** Every adapter reads
  session logs after the client already wrote them. Nothing in Phase 1
  blocks, intercepts, or modifies an agent's action in real time. Any
  copy implying real-time protection before Phase 2 ships is false
  advertising.

## Phase 2 (roadmap): enforcement — designed, not built

Phase 1 is accountability only: watch, record, prove the record wasn't
edited, triage. Phase 2 is the teeth — moving from "AgentBench told you
what happened" to "AgentBench can say no before it happens" — and it is
**design only** in this codebase right now. The seam types exist
(`accountability/policy/decision.py`, `accountability/policy/engine.py`,
`SourceAdapter.supports_interception`); the real engine and any hook-based
interception adapter are not built.

### The policy model (seam types, already shipped)

```python
class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
```

A real Phase 2 engine (not built) would read a `.agentbench/policy.yml`
(per-rule decision overrides, a protected-path DENY list, an approver +
fail-open/closed timeout) and return real verdicts. Design target
mapping: `critical` severity → `REQUIRE_APPROVAL` (configurable down to
`DENY`), `warning` severity → `ALLOW` + notify. `PolicyEngine.evaluate()`
must stay synchronous and side-effect-free (regex/in-memory only, no
file/network I/O) so a future hook adapter can call it inside a tight
latency budget without a redesign.

### Per-client interception reality-check

| Client | Phase 1 today | Phase 2 real-time interception? |
|---|---|---|
| Claude Code | tails `~/.claude/projects/*/*.jsonl` post-write | **Plausible** via a PreToolUse hook returning allow/deny/ask → a new `ClaudeCodeHookAdapter`. Exact hook schema/latency needs verification at Phase 2 kickoff, not assumed now. |
| Codex CLI | tails `~/.codex/sessions/.../rollout-*.jsonl` post-hoc | **Unconfirmed.** Codex has built-in approval modes but no confirmed third-party pre-exec hook. Don't scope Phase 2 effort against this until verified. |
| Cursor | re-parses `state.vscdb` per poll | **Not external interception.** Best case is writing Cursor's own allow/deny config — config authoring, not enforcement. Cursor's schema is reverse-engineered and undocumented; "best-effort" stays the qualifier regardless of how confident "security" framing might sound. |
| Antigravity | detect-only | No interception story yet. |

**Bottom line:** real-time ALLOW/DENY/REQUIRE_APPROVAL is credibly
buildable for Claude Code only, near-term. `REQUIRE_APPROVAL` for Claude
Code would delegate to the client's own "ask" UX (the hook returns
`"ask"`) — no separate AgentBench approval UI needed. Interception
capability is per-adapter and opt-in
(`SourceAdapter.supports_interception`, default `False` everywhere in
Phase 1); nothing here is promised for Codex, Cursor, or Antigravity.

## Design notes specific to accountability

- **No heartbeat rows in the hash-chained `events` table.** Only real
  alert events get appended and chained. Session-seen/bookkeeping
  tracking, if it exists at all, would live in a separate non-chained
  table — every chained row is a genuine alert, never a "checked in,
  nothing to report" ping.
- **Incidents are mutable by design and deliberately not chained.**
  Status/note/resolution are meant to change as someone works the
  backlog; mutability there is exactly what the `events` chain exists to
  catch elsewhere. Resolving or acknowledging an incident never touches
  the chained `events` table — `audit verify` still passes after any
  incident status change.
- **Global audit trail, not per-project.** Default path is
  `~/.agentbench/audit.db` (one machine-wide trail across every project
  you watch), overridable per-invocation with `--audit-db` / `--db`.

## Everything stays local

Watch mode reads local session files and writes to a local SQLite
database. Nothing is uploaded anywhere. Desktop notifications, when
enabled, are OS-native popups — no telemetry, no external service.
