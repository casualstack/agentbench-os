# Enforcement (Phase 2)

AgentBench's watch/audit features *observe* what an agent did, after the fact.
**Enforcement** lets AgentBench step in *before* a risky tool call runs and
**allow**, **ask**, or **deny** it — in real time, for Claude Code.

It's built on Claude Code's [PreToolUse hook](https://docs.claude.com/en/docs/claude-code/hooks):
`agentbench init` registers `agentbench hook` as that hook, and a
`.agentbench/policy.yml` decides what to do with each tool call.

## Quickstart

```bash
# In your project:
agentbench init
```

That does two things, both reversible:

1. Merges an `agentbench hook` PreToolUse entry into `.claude/settings.json`
   (existing hooks and settings are preserved).
2. Writes a starter `.agentbench/policy.yml` (only if you don't already have one).

New Claude Code sessions started in that folder will now route every
`Write`/`Edit`/`MultiEdit`/`Bash` call through AgentBench first.

To turn it off: delete `.agentbench/policy.yml` (back to observe-only), or
remove the `agentbench hook` entry from `.claude/settings.json` (fully off).

## The policy file

```yaml
version: 1

defaults:            # action for any alerting step, by severity
  warning: allow     # allow | ask | deny
  critical: ask

rules:               # per-rule overrides (rule ids from docs/ACCOUNTABILITY.md)
  secret_file_write: deny
  potential_secret_exposure: deny

protected_paths:     # writes to a matching glob are always denied
  - ".env*"
  - ".github/workflows/**"

on_error: allow      # fail open (never wedge your agent) | deny (fail closed)
```

Precedence: a repo-local `./.agentbench/policy.yml` wins over a global
`~/.agentbench/policy.yml`. If neither exists, enforcement is **observe-only**
(everything is allowed; alerts are still recorded).

### How a decision is made

For each tool call, in order:

1. A **write to a `protected_paths` glob** → `deny`.
2. Otherwise, the **most restrictive** action across the alerts the step
   raises, where each alert's action is its per-rule override or the
   per-severity default (`deny` > `ask` > `allow`).
3. No protected-path hit and no alerts → `allow`.

The three actions map onto Claude Code's permission model:

| Policy action | Claude Code result |
|---|---|
| `allow` | AgentBench stays out of the way; normal permission flow |
| `ask` | Forces a human approval prompt (`permissionDecision: "ask"`) |
| `deny` | Blocks the call before it runs (`permissionDecision: "deny"`) |

`ask` deliberately reuses Claude Code's **native** approval prompt — AgentBench
does not build its own.

## Every decision is accountable

Enforcement decisions that matter (any `deny`/`ask`, and any step that raised an
alert) are appended to the same **hash-chained audit trail** as observed
alerts, with the decision recorded in the (hashed, tamper-evident) event.
They show up in `agentbench incidents list`, `/api/incidents`, and
`agentbench audit export`, prefixed `[Blocked]` / `[Approval required]` /
`[Allowed]`. Benign, non-alerting `allow`s are not recorded (same discipline as
watch mode — no noise rows). `agentbench audit verify` still proves the chain
is intact.

## Guarantees vs. non-guarantees

Being explicit here is the point of the product.

**What enforcement guarantees**

- For **Claude Code sessions where you ran `agentbench init`**, matching
  `Write`/`Edit`/`MultiEdit`/`Bash` calls are evaluated *before* they run and
  can be blocked or gated on human approval.
- Every enforcement decision worth recording is written to the tamper-evident
  audit trail.
- It **fails safe**: any error in the hook or a malformed policy file falls
  back to your `on_error` setting (default `allow`), and never crashes or
  wedges the agent.

**What it does _not_ guarantee**

- **It is not a sandbox.** Rules are heuristic (the same regex rules watch mode
  uses). A determined agent could phrase a command to dodge a pattern, or shell
  out to do indirectly what a blocked tool would have done directly. Treat this
  as a strong guardrail, not a security boundary.
- **Claude Code only.** Codex, Cursor, and Antigravity remain observation-only —
  they expose no pre-execution interception point AgentBench can use today.
- **Only where installed.** A session started in a folder without the hook (or
  before `init`) is not enforced.
- **Audit tamper-evidence is unchanged** from Phase 1: it proves AgentBench's
  own local `audit.db` wasn't edited after the fact. It is plain SHA-256
  chaining, not cryptographic security against a determined local attacker who
  recomputes the chain, and it says nothing about whether the session log was
  scrubbed before AgentBench saw it. See [ACCOUNTABILITY.md](ACCOUNTABILITY.md).

## Troubleshooting

- **Nothing is being blocked.** The hook shells out to `agentbench hook`, so
  `agentbench` must be on the `PATH` of the environment Claude Code runs in. If
  you installed into a virtualenv, either activate it before launching Claude
  Code or point the hook at the absolute path (edit the `command` in
  `.claude/settings.json`). Also confirm a `.agentbench/policy.yml` exists —
  without one, enforcement is observe-only by design.
- **Everything is allowed even though my policy says deny.** Policy is resolved
  relative to the session's working directory. A repo-local
  `./.agentbench/policy.yml` only applies to sessions working in that repo; use
  `~/.agentbench/policy.yml` for a machine-wide default.
- **`watch` and the hook together.** The hook records pre-execution; `watch`
  records post-hoc. Running both over the same session can double-record an
  event. Pick one per session (enforce with `init`, or observe with `watch`).

## Compatibility

Tested against Claude Code's PreToolUse hook JSON contract
(`hookSpecificOutput.permissionDecision` = `allow`/`ask`/`deny`). If a future
Claude Code release changes that contract, the mapping in
`accountability/hook.py` is the single place to update.
