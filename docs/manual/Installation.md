# Installation

This page covers every way to install AgentBench OS: from PyPI, from a clone
of the repository, the desktop app, and the optional extras.

Repository: https://github.com/casualstack/agentbench-os

## From PyPI (recommended)

```bash
pip install agentbench
agentbench --help
```

Published from the first tagged `v0.2.0` release onward, via the
`.github/workflows/publish.yml` trusted-publishing workflow. If your
environment doesn't have it yet, use the from-source install below — the two
are otherwise identical.

## Requirements

- Python 3.11 or later (the project targets 3.11 and 3.12; `pyproject.toml`
  requires `>=3.11`)
- `pip`
- Git, to clone the repository

Core runtime dependencies (installed automatically): `pydantic>=2.0` and
`pyyaml>=6.0`.

## CLI install (from source)

```bash
git clone https://github.com/casualstack/agentbench-os
cd agentbench-os
pip install -e ".[dev]"
```

The `-e` (editable) install is what the repo's own README, CI workflow, and
GitHub Action all use. The `[dev]` extra adds `pytest>=8.0` and
`pytest-cov>=4.0`, needed if you want to run the test suite
(`pytest -q`) but not required just to use the `agentbench` CLI.

For the CLI alone, without dev tooling:

```bash
pip install -e .
```

Either form registers the `agentbench` console script (defined in
`pyproject.toml` as `agentbench = "agentbench.cli.main:main"`). Confirm it
worked:

```bash
agentbench --help
```

If you only want to install in a CI job without editable mode, `pip install .`
works the same way; editable mode is convenient for local development because
edits to `src/agentbench` take effect without reinstalling.

## Optional extras

| Extra | Adds | What it unlocks |
|-------|------|------------------|
| `dev` | `pytest`, `pytest-cov` | Running the project's own test suite |
| `app` | `pywebview>=5.0` | `agentbench app`, the native desktop window |
| `notify` | `plyer>=2.1` | A native cross-platform backend for `agentbench watch` desktop notifications |

Extras combine:

```bash
pip install -e ".[dev,app,notify]"
```

`agentbench ui` (the browser-tab client) needs none of these extras - it
uses only the Python standard library's HTTP server. `agentbench app` (the
native window) needs `app`. `agentbench watch` works with no extras at all;
`notify` only improves how its desktop notifications are delivered (see
[Watch Mode](Watch%20Mode.md#desktop-notifications)).

## Desktop app builds

AgentBench ships standalone desktop builds for Windows, macOS, and Linux
that need no local Python install to run. There are two ways to get one:

### Download a prebuilt release

Every tagged release (`vX.Y.Z`) attaches a zipped build for each platform to
the GitHub release: https://github.com/casualstack/agentbench-os/releases

A build from any commit (not just tagged releases) is also available as a
CI artifact from the `Desktop Builds` workflow
(`.github/workflows/desktop-builds.yml`): open the workflow run for that
commit on the Actions tab and download `AgentBench-windows`,
`AgentBench-macos`, or `AgentBench-linux`.

### Build locally

Windows:

```powershell
pip install -e ".[app]" pyinstaller
.\scripts\build_desktop.ps1    # -> dist\AgentBench\AgentBench.exe
```

macOS / Linux:

```bash
pip install -e ".[app]" pyinstaller
./scripts/build_desktop.sh     # -> dist/AgentBench.app (macOS) or dist/AgentBench (Linux)
```

Both scripts invoke PyInstaller against `AgentBench.spec`, which is the
single source of truth for build options (icon, embedded version resource,
one-dir layout) - the same spec the CI build uses. The output is a folder
(`dist/AgentBench/`), not a single executable file; see below for why.

Linux builds additionally need pywebview's GTK backend system packages
(GObject introspection and WebKitGTK). The exact `apt-get install` list is
kept current in the `Install Linux GUI dependencies` step of
`.github/workflows/desktop-builds.yml` - check that file for the packages
your distro needs, since the list is tied to a specific Ubuntu image
version. On macOS, Pillow (`pip install pillow`) lets PyInstaller convert
the app icon automatically; CI installs it alongside `pyinstaller`.

### Windows SmartScreen and macOS Gatekeeper warnings

AgentBench's desktop builds are not signed with an Authenticode certificate
as of v0.2.0. Windows SmartScreen will say it "protected your PC" the first
time you run a downloaded build - this is expected and not specific to
AgentBench; SmartScreen warns on any unsigned binary. Click **More info**,
then **Run anyway**, but only do this for a build from the official
[GitHub release](https://github.com/casualstack/agentbench-os/releases) or
a [CI artifact](https://github.com/casualstack/agentbench-os/actions/workflows/desktop-builds.yml)
you trust. macOS Gatekeeper shows an equivalent warning for the unsigned
`.app`; right-click it and choose **Open** to bypass it once.

Two build decisions already reduce false positives from these heuristics:
the build is one-dir rather than one-file (a self-extracting one-file exe
is exactly the pattern SmartScreen distrusts), and it embeds a real Windows
version resource (`AgentBench.version.txt`) instead of shipping with none.

If you would rather avoid the warning entirely, build from source as shown
above - a build you compiled yourself has nothing to be flagged for.
Code-signing (an Authenticode/EV certificate plus a `signtool` step in CI)
is tracked as follow-up work and is not implemented in the repository yet.

## Verifying the install

```bash
agentbench --help
pytest -q          # only if you installed the [dev] extra
```

`agentbench --help` should list ten subcommands, in two groups:

- **Security & accountability:** `watch`, `init`, `diff`, `incidents`, `audit`
- **Eval / benchmarking:** `run`, `gate`, `matrix`, `ui`, `app`

(`init` turns on real-time enforcement for Claude Code — see
[Enforcement](../ENFORCEMENT.md).)

## Next

[Quickstart](Quickstart.md) walks through watch mode, enforcement, and your
first gate run. [Desktop App](Desktop%20App.md) covers the app in more depth
once it is installed.
