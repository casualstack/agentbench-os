# Watch mode — zero-config agent monitoring

Watch mode is the "just works" side of AgentBench's accountability pillar
(see [ACCOUNTABILITY.md](ACCOUNTABILITY.md) for the pillar overview). No
task JSON, no trajectory exports: AgentBench finds the AI coding agent
sessions already recorded on your machine, checks them, and keeps
watching new activity live.

```bash
agentbench watch
```

```
Found: Claude Code, Cursor, Codex CLI
Checked 19 recorded session(s).
[!] Deleted a test assertion — claude-code session 6e19a2f1 in C:\work\myrepo
    The agent removed a check from tests/test_calc.py. Tests that no longer
    assert anything will pass even when the code is broken.

Watching for new agent activity... (Ctrl+C to stop)
```

## What it watches

AgentBench discovers sessions through a pluggable **source adapter** per
client (`src/agentbench/adapters/`). Adding a new client is one
subclass of `SourceAdapter` registered in `adapters.ADAPTERS`.

| Agent | Where sessions live | Status |
|-------|---------------------|--------|
| Claude Code | `~/.claude/projects/<project>/<session>.jsonl` | First-class (live tail) |
| Codex CLI | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | First-class (live tail) |
| Cursor | SQLite workspace storage (`state.vscdb`) | Parsed, best-effort |
| Antigravity | best-effort home/appdata dir | Detected — parsing coming |

Claude Code and Codex CLI are both append-only JSONL, so they're tailed
incrementally. Cursor's store is a SQLite database with no append log, so
its sessions are re-parsed and diffed by step count on each poll. The
Cursor schema is undocumented and reverse-engineered — parsing is defensive
and degrades to "detected only" if the database can't be read.

Codex rollout files record shell commands (`shell_command` function calls)
and file edits (`apply_patch` custom tool calls, including add/update/delete
hunks) — both normalize into the same `run_command`/`write_file`/
`str_replace` steps as the other clients, so the full default rule set
(deleted/weakened assertions, destructive commands, secret writes, ...)
applies to Codex sessions too.

## Default rules

Every rule ships on by default and needs zero configuration.

| Rule | Severity | Fires when the agent... |
|------|----------|------------------------|
| `deleted_assertion` | critical | removes an assertion from a test file |
| `weakened_assertion` | critical | replaces a real check with one that always passes (`assert True`, `.toBe(true)`, …) |
| `skipped_test` | critical | marks a test as skipped/disabled |
| `test_file_overwritten` | warning | rewrites an entire test file |
| `test_file_modified` | warning | edits a test file at all |
| `out_of_project_write` | critical | writes outside the folder it was working in |
| `secret_file_write` | critical | writes to a secret-shaped file (`.env`, `*.pem`, `id_rsa`, `credentials.json`, …) |
| `hook_bypass` | critical | skips git safety hooks (`--no-verify`, `--no-gpg-sign`, `HUSKY=0`, …) |
| `destructive_command` | critical | runs `rm -rf`, `git reset --hard`, force-push, etc. |
| `network_command` | warning | runs curl/wget/HTTP commands (your own localhost dev server doesn't count) |
| `privilege_escalation_command` | critical | runs sudo/ACL/permission-bypass style commands |
| `possible_data_exfiltration` | warning | runs commands that can upload/sync local data elsewhere |
| `potential_secret_exposure` | critical | writes content that looks like hardcoded credentials |
| `ci_guardrail_touched` | warning | edits CI workflows/action policy-critical files |

Writes to the agent's own config area (`~/.claude/...`, e.g. memory files)
are expected behavior and never alert.

## CLI options

```bash
agentbench watch                     # check history, then watch live
agentbench watch --project C:\work\myrepo   # only sessions in that folder
agentbench watch --once              # check recorded sessions and exit
agentbench watch --once --fail-on-alert     # exit 1 on critical findings (CI-friendly)
agentbench watch --live-only         # ignore history; alert on new activity only
agentbench watch --interval 5        # seconds between checks (default 2)
agentbench watch --no-notify         # never send desktop notifications
agentbench watch --once --digest report.md   # write a shareable markdown report
```

## /diff reports

For trajectory-to-trajectory accountability diffs:

```bash
agentbench diff \
  --baseline .agentbench/baseline.json \
  --candidate .agentbench/last-run.json \
  --output build/diff-report.md
```

Use `--fail-on-change` when you want `/diff` to fail automation on change.

## Desktop notifications

While the live loop is running, each poll that finds new alerts raises a
single batched desktop notification (e.g. *"AgentBench: 3 issues in myrepo
(1 critical)"*) — not one toast per alert, so loading a project's history
never floods you. Notifications are on by default for the live loop and off
for `--once` (the CI/scripting path); toggle with `--notify` / `--no-notify`.

Delivery is best-effort and needs no setup: AgentBench uses the OS's built-in
notifier (`osascript` on macOS, `notify-send` on Linux, a PowerShell toast on
Windows). Install `agentbench[notify]` for a native cross-platform backend.
If no backend is available, notifications silently do nothing — the terminal
output is unaffected.

## Session digest

`--digest PATH` writes a plain-English markdown report of every watched
session — client, project, model, step count, and alerts grouped
critical-first — after the run (with `--once`, right away; with the live
loop, on Ctrl+C). It's meant to be shared: paste it into an issue or a
message to show exactly what an agent did.

## Audit trail

Every alert `watch` raises is appended to a local, hash-chained SQLite
store by default — `agentbench watch` records automatically, no separate
step needed. Opt out with `--no-audit-log`, or point at a different file
with `--audit-db PATH` (default: the global `~/.agentbench/audit.db`,
shared across every project you watch on this machine).

```bash
agentbench audit verify                      # OK, or the first tampered row + exit 1
agentbench audit verify --db build/audit.db  # check a specific database
```

`audit verify` walks the chain and reports either `OK` or the id of the
first row whose hash no longer matches its content — see
[ACCOUNTABILITY.md](ACCOUNTABILITY.md) for exactly what that does and
doesn't prove (short version: it proves AgentBench's own record wasn't
edited after being written, not that the underlying session log was
never touched).

```bash
agentbench audit export --output history.md                      # durable digest, like --digest but historical
agentbench audit export --output history.json --format json      # for scripting
agentbench audit export --output history.md --project C:\work\myrepo --since 2026-07-01T00:00:00Z
```

`audit export` is `watch --digest`'s durable, historical counterpart: same
markdown shape, sourced from the persisted audit trail instead of the
current run's in-memory state, with each alert annotated with its
incident status.

## Incidents

Alerts in the terminal or a digest are a stream; incidents are a queryable
backlog with disposition. Every alert becomes exactly one incident
(1:1 — no cross-alert dedup or grouping in Phase 1, see
[ACCOUNTABILITY.md](ACCOUNTABILITY.md)), starting in `open` status.

```bash
agentbench incidents list                              # everything, newest last
agentbench incidents list --status open                # only what's unresolved
agentbench incidents list --severity critical --project C:\work\myrepo
agentbench incidents show <incident-id>                 # full detail for one incident
agentbench incidents ack <incident-id> --note "reviewed, waiting on fix"
agentbench incidents resolve <incident-id> --note "fixed in a1b2c3d"
```

Acknowledging or resolving an incident never touches the hash-chained
`events` table — `audit verify` still reports `OK` after any status
change, since incident status is deliberately outside the chain (it's
meant to be mutated; the chain exists to catch mutation elsewhere).

## How it relates to tasks and oracles

Watch mode and the eval gate share one engine. Session logs are normalized
into the same trajectory step vocabulary the oracles understand
(`write_file`, `str_replace`, `run_command`), so a watched session can later
be replayed through `agentbench run` / `agentbench gate` against real task
oracles. Watch rules are the zero-config defaults; task oracles
(docs/ORACLE_SPEC.md) are the precise, per-repo contracts.

## Design notes

- Polling tail (default every 2s), not filesystem events: append-only JSONL
  needs nothing fancier, and it behaves identically on Windows/macOS/Linux.
- Corrupt or partial trailing lines are expected in live files and skipped;
  a partial line is buffered until its remainder arrives.
- Everything stays on your machine. Watch mode reads local files and never
  sends anything anywhere.
