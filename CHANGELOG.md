# Changelog

All notable changes to AgentBench OS are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — "The Teeth"

The release that makes the "security" half of the pitch real: AgentBench can
now **block** a risky Claude Code tool call before it runs, not just record it
after the fact. Also the first release published to PyPI.

### Added

- **Real-time enforcement for Claude Code** (Phase 2). `agentbench init`
  installs a PreToolUse hook and a starter `.agentbench/policy.yml`; matching
  `Write`/`Edit`/`MultiEdit`/`Bash` calls are then evaluated before they run and
  can be **allowed**, **asked** (native approval prompt), or **denied**.
  Opt-in, reversible, and inert until a policy file exists. See
  [docs/ENFORCEMENT.md](docs/ENFORCEMENT.md).
- **Policy engine** — `ConfigPolicyEngine` driven by a validated
  `.agentbench/policy.yml` (per-severity defaults, per-rule overrides,
  `protected_paths` deny-globs, `on_error` fail-open/closed). Config is loaded
  once; `evaluate()` stays synchronous and side-effect-free.
- **`agentbench init`** and the plumbing **`agentbench hook`** subcommands.
- Enforcement decisions are recorded to the hash-chained audit trail
  (`record_from_verdict`), tamper-evident and visible in `incidents list`,
  `/api/incidents`, and `audit export`.
- `ClaudeCodeAdapter.supports_interception` is now `True` — the Phase 2 seam is
  honestly consumed.
- **PyPI publishing** via a Trusted-Publishing (OIDC) workflow
  (`.github/workflows/publish.yml`), with a TestPyPI dry run.
- **Cross-platform CI**: the test matrix now runs on Ubuntu, Windows, and macOS
  (previously Ubuntu only).
- This CHANGELOG.

### Changed

- Enforcement fails **safe**: any hook error or malformed policy falls back to
  the configured `on_error` (default `allow`) and never wedges the agent.
- The package version is now single-sourced from
  `src/agentbench/__init__.py` (pyproject reads it dynamically), removing the
  `pyproject.toml` / `__init__.py` drift risk.
- Docs corrected for the accountability pivot: `docs/manual/Installation.md`
  now lists all ten CLI commands (previously seven) and the PyPI install path.
- Package metadata refreshed (Beta status, security topic/keywords, Python 3.13
  classifier).

### Notes on scope

Enforcement is a strong guardrail, **not a sandbox**: rules are heuristic and an
agent could shell out around a blocked tool. Interception is Claude Code only.
Audit tamper-evidence is unchanged (local-DB SHA-256 chaining, not cryptographic
security against a determined local attacker). See
[docs/ACCOUNTABILITY.md](docs/ACCOUNTABILITY.md) and
[docs/ENFORCEMENT.md](docs/ENFORCEMENT.md) for the full guarantees/non-guarantees.

## [0.1.0]

- Initial alpha: watch mode with zero-config rules, hash-chained audit trail,
  incident backlog, dashboard, and the property-oracle eval/gate/matrix suite
  plus GitHub Action.

[Unreleased]: https://github.com/casualstack/agentbench-os/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/casualstack/agentbench-os/releases/tag/v0.2.0
[0.1.0]: https://github.com/casualstack/agentbench-os/releases/tag/v0.1.0
