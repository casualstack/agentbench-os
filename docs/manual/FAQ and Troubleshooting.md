# FAQ and Troubleshooting

## Watch mode can't find my sessions

`agentbench watch` reports "No AI coding agents found on this machine yet"
and exits `1` when no adapter's `detect()` returns true. Detection checks
fixed default locations under `Path.home()`:

- Claude Code: `~/.claude/projects/` must exist as a directory
- Codex CLI: `~/.codex/sessions/` must exist as a directory
- Cursor: at least one `.../User/workspaceStorage/*/state.vscdb` must exist
  under one of several platform-specific roots (see
  [Watch Mode](Watch%20Mode.md#clients-and-fidelity))

If you use a client at a non-default install location, or your home
directory is redirected (some corporate Windows setups symlink
`%USERPROFILE%` elsewhere), detection will miss it - there is no CLI flag
in v0.1.0 to point watch mode at a custom home directory.

If a client *is* detected but a specific session doesn't show alerts,
remember `--project PATH` filters to sessions whose recorded working
directory is under that folder; a session working elsewhere is discovered
but silently skipped from output. Drop `--project` to see everything.

For Cursor specifically: `CursorAdapter` is intentionally defensive. A
locked database (the IDE has it open), an unrecognized schema, or a corrupt
blob all degrade to "detected, no sessions parsed" rather than raising an
error - so Cursor appearing in the `Found:` line with zero sessions or
alerts is expected, given Cursor's storage format is undocumented and
reverse-engineered. See [Watch Mode](Watch%20Mode.md#clients-and-fidelity).

Antigravity will always show as "detected - parsing coming soon" and
contribute zero sessions - its adapter has no parser implemented yet.

## Windows Defender / SmartScreen warnings on the desktop app

Expected, and not specific to AgentBench: the desktop builds are not signed
with an Authenticode certificate as of v0.1.0, and SmartScreen warns on any
unsigned binary. Click **More info**, then **Run anyway** - but only if you
downloaded the build from the official
[GitHub release](https://github.com/casualstack/agentbench-os/releases) or
a [CI artifact](https://github.com/casualstack/agentbench-os/actions/workflows/desktop-builds.yml)
you trust. If you'd rather not see the warning at all, build from source
(covered in [Installation](Installation.md#desktop-app-builds)); a binary
you compiled yourself has nothing for SmartScreen to flag. macOS Gatekeeper
shows an equivalent warning for the unsigned `.app` - right-click and choose
**Open** to bypass it once. Code-signing is tracked as follow-up work, not
implemented in the repo yet.

## Oracle import and validation errors

Two distinct failure modes look similar but come from different layers:

**Unknown oracle type at task load time.** If a task JSON's `oracles`
array references a `type` not in `KNOWN_ORACLE_TYPES` (`test_must_pass`,
`file_not_modified`, `no_network`, `assertion_exists` in v0.1.0),
`EvalTask.from_file()` raises `ValidationError` before any evaluation
happens - "oracles[N] has unknown type 'X'; known: [...]". Either a typo in
the task JSON, or a custom oracle registered in Python but not added to
`KNOWN_ORACLE_TYPES` / `ORACLE_REQUIRED_PARAMS` in
`src/agentbench/eval/dsl/validator.py` (see
[Writing Oracles](Writing%20Oracles.md#writing-a-new-oracle-type)).

**Unregistered oracle type at check time.** If a new `OracleCheck`
subclass is decorated with `@register_oracle` but its module is never
imported before evaluation runs (built-ins are imported explicitly at the
top of `src/agentbench/eval/gate/evaluator.py`), `get_oracle()` raises
`ValueError: Unknown oracle type` at evaluation time even though the task
JSON validated fine. Fix by adding the import to `evaluator.py`.

**Missing required params.** Each oracle type has required params checked
by `validate_oracle()` - `test_must_pass` needs `command`,
`file_not_modified` needs `path`, `assertion_exists` needs both `path` and
`pattern`, `no_network` needs none. A missing param fails validation with
the param name, before the oracle's own `check()` method - which also
defensively re-checks and returns a failed result rather than raising -
ever runs.

## A gate is blocking a PR I believe is correct

Read the oracle message first - `agentbench run` / `agentbench gate` print
one line per oracle naming exactly which one failed and why (file path,
missing pattern, command exit code). From there:

- **`file_not_modified` failed on a file that should have been editable.**
  The task's protected-path list is wrong for what you're doing now; either
  the task needs updating (agents are allowed to touch that file for this
  change) or the trajectory really did touch something it shouldn't have.
- **`assertion_exists` failed but the logic is still correct.** The regex
  is too literal - it's matching exact original code, and a legitimate
  refactor changed the matched text without weakening the check it
  represents. Loosen the pattern to match the property, not the exact
  original wording (see the pitfalls in
  [Writing Oracles](Writing%20Oracles.md#pitfalls)).
- **`test_must_pass` failed but the tests pass locally.** The oracle runs
  its command inside the *replayed* workspace - a fresh temp directory built
  from `task.workspace` plus the trajectory's file edits - not your full
  local checkout. Dependencies, config, or files your test command needs
  that aren't part of `task.workspace` will cause this mismatch. Either add
  the missing files to `task.workspace` or adjust the command.
- **Gate fails on tasks unrelated to what the trajectory touched.**
  `agentbench gate` without `--manifest` evaluates every task JSON in the
  tasks directory against one trajectory; a trajectory that only edits two
  files will fail any task whose oracles reference other files. Use
  `--manifest` to scope the run to compatible tasks (see
  [CI Integration](CI%20Integration.md)).

If none of the above explains it, the oracle itself may be encoding the
wrong property for what you actually want enforced - oracles check exactly
what they're written to check, nothing more contextual than that. Revisit
the task JSON.

## Reporting issues

File a GitHub issue: https://github.com/casualstack/agentbench-os/issues.
Include the command you ran, the task/trajectory JSON (or a minimal
reproduction), and the full oracle output - the same detail the CLI already
prints (`[FAIL] oracle_type: message`) is normally enough to diagnose.

## License

MIT. See `LICENSE` in the repository root. AgentBench OS is free to use,
modify, and redistribute under those terms, including inside a commercial
CI pipeline.

## How this relates to my existing CI test suite

They check different things and run alongside each other, not instead of
one another. Your test suite checks whether the *current code* is correct;
AgentBench checks whether the *agent's process that produced it* violated
constraints you set - scope, protected files, network access, assertion
integrity - which a green test suite alone cannot express, since a suite
can be made to pass by deleting what it checks (see
[Quickstart](Quickstart.md)). `test_must_pass` even lets an oracle wrap your
existing test command directly. See
[Concepts and Glossary](Concepts%20and%20Glossary.md#philosophy) for the
fuller argument and [CI Integration](CI%20Integration.md) for the two jobs
running side by side.

## Related

- [Watch Mode](Watch%20Mode.md) - adapter fidelity per client, in depth
- [Writing Oracles](Writing%20Oracles.md) - oracle API, pitfalls, and how to extend it
- [CI Integration](CI%20Integration.md) - the gate workflow this page's troubleshooting steps assume
