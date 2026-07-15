# Welcome

AgentBench OS is security & accountability for AI coding agents: it
watches the AI coding sessions already running on your machine, keeps a
durable, tamper-evident record of what they did, and raises plain-English
alerts the moment one cuts a corner. The same engine also gates recorded
agent runs on pull requests with deterministic property checks — a hard
pass or fail, no fuzzy score.

Source: https://github.com/casualstack/agentbench-os (MIT license, v0.1.0).

## The problem

AI coding agents produce diffs fast, and the diffs frequently look correct
without being correct. An agent asked to fix a failing test can make the
test pass by deleting the assertion instead of fixing the code. An agent
asked to touch one file can quietly edit a dozen. An agent debugging offline
can run `pip install` mid-task and change what "passing" even means. None of
this shows up in a code review that only reads the final diff, because the
diff is exactly what the agent wants you to see. And once you've seen it and
moved on, there's usually no durable record of what actually happened.

AgentBench OS exists to check the process, not just the artifact: what the
agent actually did, step by step, against rules you can write down and run
in CI or watch live — and to keep an account of that you can trust.

## Three core ideas

**Session watching & accountability.** `agentbench watch` finds the AI
coding sessions already on your machine (Claude Code, Cursor, Codex CLI,
and detects Antigravity), tails them as they happen, and raises
plain-English alerts the moment an agent does something like weaken an
assertion or write to a `.env` file. Every alert is recorded to a local,
hash-chained audit trail — `agentbench audit verify` can prove that record
hasn't been silently edited since it was written — and surfaced as a
queryable incident with disposition (`agentbench incidents list|ack|resolve`),
not just a scrolling terminal stream. Zero configuration, nothing leaves
your machine. See [Watch Mode](Watch%20Mode.md).

**Property oracles.** An oracle is a small, deterministic check against a
recorded agent run: "the test suite still exits 0," "this file is
byte-identical to before," "no network access happened," "this regex still
matches." Oracles do not evaluate quality or style. They check one property
and return pass or fail, with a message. See
[Writing Oracles](Writing%20Oracles.md) for the oracle types that ship today
(`test_must_pass`, `file_not_modified`, `no_network`, `assertion_exists`)
and how to add your own.

**Deterministic gates.** A gate runs a set of oracles against a recorded
trajectory (a JSON log of the agent's tool calls) replayed into a clean
workspace, and fails the moment any oracle fails. There is no partial
credit and no score to interpret. `agentbench gate` exits 1 if any task
fails, which is what branch protection rules and CI jobs need. See
[CI Integration](CI%20Integration.md).

## What AgentBench OS is not

- **It is not an eval score.** There is a benchmark matrix runner
  (`agentbench matrix`) for comparing pass rates across models and prompts,
  but every underlying check is still a hard pass/fail oracle. AgentBench
  never produces a fuzzy quality number for a single run; it produces PASS
  or FAIL.
- **It is not an LLM judge.** No oracle asks a model whether code "looks
  right." Checks are regex matches, file diffs, and shell command exit
  codes. The tradeoff is real: oracles catch what you thought to check for,
  nothing more, and nothing less predictably.
- **It is not a live agent runner.** The MVP evaluates a recorded
  trajectory (a JSON file of tool calls) against a task's initial
  workspace. It does not drive Cursor or Claude Code itself. Watch mode is
  the exception that observes agents live, but even there it reads session
  logs rather than controlling the agent — nothing blocks or intercepts an
  action yet.
- **The audit trail is not proof the agent's actions weren't hidden.**
  `agentbench audit verify` proves AgentBench's own local record wasn't
  silently edited after it was written. It says nothing about whether the
  underlying session log was edited before AgentBench ever read it. See
  [Watch Mode](Watch%20Mode.md) for the exact scope.

## Where to go next

- [Installation](Installation.md) - every real way to get AgentBench OS running
- [Quickstart](Quickstart.md) - zero to your first gate result in about ten minutes
- [Writing Oracles](Writing%20Oracles.md) - the oracle API, patterns, and how to extend it
- [Watch Mode](Watch%20Mode.md) - live session watching, adapters, and the default rule set
- [Desktop App](Desktop%20App.md) - the native/browser client built on the same engine
- [CI Integration](CI%20Integration.md) - gating pull requests with the GitHub Action
- [Concepts and Glossary](Concepts%20and%20Glossary.md) - precise definitions and the philosophy behind them
- [FAQ and Troubleshooting](FAQ%20and%20Troubleshooting.md) - common failure modes and fixes

Repository: https://github.com/casualstack/agentbench-os
