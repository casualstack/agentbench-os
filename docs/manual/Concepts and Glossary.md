# Concepts and Glossary

Precise definitions for the terms used throughout these docs, matched to
where each is defined in the source.

## Glossary

**Task.** A JSON document (`agentbench.eval.models.EvalTask`) describing an
eval: an `id`, `name`, `description`, `prompt` (what the agent was asked to
do), a `workspace` (the starting file contents), and a list of `oracles`
that must all pass. Tasks live as files, typically under `tasks/` or
`.agentbench/tasks/`. See [Writing Oracles](Writing%20Oracles.md).

**Oracle.** A property-based check (`agentbench.eval.oracles.base.OracleCheck`)
run against a replayed workspace and/or a trajectory. An oracle checks one
property - "this shell command exits 0," "this file is unchanged," "no
network access happened," "this regex still matches" - and returns pass or
fail with a message (`OracleResult`). Oracles are registered by a string
`oracle_type` (`test_must_pass`, `file_not_modified`, `no_network`,
`assertion_exists` ship in v0.1.0) and referenced from a task's `oracles`
array by that type name plus parameters. See
[Writing Oracles](Writing%20Oracles.md).

**Trajectory.** A JSON document (`agentbench.core.trajectory.Trajectory`)
recording an agent run as an ordered list of `steps` - tool calls like
`write_file`, `str_replace`, `run_command`. A trajectory is a record of what
an agent *did*, independent of any task; the same trajectory can be
evaluated against different tasks, and a task can be evaluated against
different trajectories to compare agent runs.

**Gate.** The act of evaluating one or more tasks against one trajectory
and producing a hard pass/fail verdict, with exit code `0` (pass) or `1`
(fail) driving CI. `agentbench gate --tasks DIR --trajectory FILE` is a
gate over every task in a directory; `agentbench run --task FILE
--trajectory FILE` is a gate over a single task. See
[CI Integration](CI%20Integration.md).

**Adapter.** A `SourceAdapter` subclass (`src/agentbench/adapters/`)
that knows how to find and parse one coding agent's session data on disk -
`detect()` (is it present?), `discover()` (enumerate sessions), and
`parse_session()` (turn one session into normalized steps). Claude Code and
Codex CLI adapters support live byte-tailing of append-only JSONL; Cursor's
adapter is a best-effort SQLite reader; Antigravity's adapter currently only
detects, without parsing. See [Watch Mode](Watch%20Mode.md).

**Session.** One recorded conversation/run of a coding agent on this
machine, as the adapter's underlying format stores it - one `.jsonl` file
for Claude Code and Codex CLI, one composer entry inside Cursor's
`state.vscdb`. `SessionWatcher` tracks per-session state (read offset, step
count, accumulated alerts) across polls.

**Rule.** A zero-config check in `src/agentbench/accountability/rules.py` that runs
against one normalized trajectory step during watch mode and produces an
`Alert` (rule name, severity, title, detail) when it fires. Rules are the
watch-mode counterpart to task oracles: no task JSON is required, every
rule ships on with sensible defaults, and alert copy is written for someone
who has never heard the word "trajectory." See
[Watch Mode](Watch%20Mode.md#default-rules) for the full rule table.

**Workspace.** The materialized file tree an oracle inspects. For task
evaluation, `AgentRunner` builds it by writing out `task.workspace`'s
initial file contents into a temp directory, then replaying the
trajectory's `file_edits()` onto it. It exists only for the duration of one
evaluation unless `keep_workspace=True` is passed to `Evaluator.evaluate()`.

**Digest.** A plain-English markdown report of everything a `SessionWatcher`
has observed - one section per session, alerts grouped critical-first -
produced by `render_digest()` (`src/agentbench/accountability/digest.py`). Written
by `agentbench watch --digest PATH` or downloaded from the desktop/browser
client's Live Watch tab.

**Manifest.** A small JSON document (`{"task_files": [...]}` or
`{"task_subset": "path/to/other-manifest.json"}`) that scopes an
`agentbench gate` run to the tasks a given trajectory is actually
compatible with, via `--manifest`. See `agentbench.eval.gate.manifest`.

**Matrix.** A benchmark configuration (`agentbench.eval.matrix`) that
runs the same set of tasks against several trajectories, each labeled with
a model/prompt pair, to compare pass rates and detect score drift against a
recorded baseline. Run with `agentbench matrix --config FILE`. This is
about comparing agents against each other over time, not about scoring a
single run - the underlying evaluation for every cell is still a hard
pass/fail gate.

## Philosophy

<a id="philosophy"></a>

AgentBench OS is built on the premise that "the agent's tests pass" is not
the same claim as "the agent did the right thing," and that the gap between
those two claims is exactly where agents cut corners: deleting an assertion
instead of fixing a bug makes a test suite green without making the code
correct. A single scalar quality score - or worse, another LLM judging the
first LLM's output - papers over this gap instead of closing it, because
both approaches ask "does this look right" rather than "does this satisfy a
property I can write down and check mechanically." AgentBench's oracles are
deliberately narrow and deterministic for this reason: a regex match, a
file-diff comparison, or a subprocess exit code either holds or it doesn't,
and a task author who writes `assertion_exists` for the specific check that
matters knows precisely what was verified and what wasn't - no interpretation
required on either side.

This is why AgentBench evaluates the trajectory, not just the diff.
Watching what an agent actually did - which files it touched, which
commands it ran, in what order - makes visible the corner-cutting that
disappears once you only look at the final code: a hook bypassed on the way
to a commit, a `.env` file written and then not mentioned again, a test
skipped rather than fixed. Check the work, not the vibes: property oracles
for the contracts you can specify ahead of time in a task file, and
zero-config watch rules for the corner-cutting patterns common enough to
flag by default without anyone having to ask. Neither replaces human review
of the agent's output; both exist to make that review start from "here is
what actually happened" instead of "here is a diff that claims to have
happened."

## Related

- [Writing Oracles](Writing%20Oracles.md) - oracle, task, trajectory, gate in practice
- [Watch Mode](Watch%20Mode.md) - adapter, session, rule, digest in practice
- [Welcome](Welcome.md) - the three core ideas these terms support
