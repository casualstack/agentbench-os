# Watch mode — zero-config agent monitoring

Watch mode is the "just works" side of AgentBench. No task JSON, no
trajectory exports: AgentBench finds the AI coding agent sessions already
recorded on your machine, checks them, and keeps watching new activity live.

```bash
agentbench watch
```

```
Found: Claude Code, Cursor (detected — support coming soon)
Checked 19 recorded session(s).
[!] Deleted a test assertion — claude-code session 6e19a2f1 in C:\work\myrepo
    The agent removed a check from tests/test_calc.py. Tests that no longer
    assert anything will pass even when the code is broken.

Watching for new agent activity... (Ctrl+C to stop)
```

## What it watches

| Agent | Where sessions live | Status |
|-------|---------------------|--------|
| Claude Code | `~/.claude/projects/<project>/<session>.jsonl` | First-class |
| Cursor | SQLite workspace storage | Detected only — parsing coming |

## Default rules

Every rule ships on by default and needs zero configuration.

| Rule | Severity | Fires when the agent... |
|------|----------|------------------------|
| `deleted_assertion` | critical | removes an assertion from a test file |
| `skipped_test` | critical | marks a test as skipped/disabled |
| `test_file_overwritten` | warning | rewrites an entire test file |
| `test_file_modified` | warning | edits a test file at all |
| `out_of_project_write` | critical | writes outside the folder it was working in |
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
