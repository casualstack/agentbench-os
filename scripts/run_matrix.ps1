# Wrapper for the AgentBench model matrix CLI.
#
# Usage:
#   .\scripts\run_matrix.ps1 [-Config PATH] [-Tasks DIR] [-Output FORMAT] [-ExtraArgs ...]
#
# Defaults:
#   Config  configs\matrix.json
#   Tasks   tasks\
#   Output  markdown

[CmdletBinding()]
param(
    [string] $Config,
    [string] $Tasks,
    [ValidateSet("markdown", "json", "csv")]
    [string] $Output = "markdown",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ExtraArgs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

if (-not $Config) {
    $Config = Join-Path $RepoRoot "configs\matrix.json"
}
if (-not $Tasks) {
    $Tasks = Join-Path $RepoRoot "tasks"
}

$srcPath = Join-Path $RepoRoot "src\agentbench"
if (-not (Get-Command agentbench -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath $srcPath)) {
    $env:PYTHONPATH = if ($env:PYTHONPATH) { "$RepoRoot\src;$env:PYTHONPATH" } else { "$RepoRoot\src" }
}

$cliArgs = @(
    "matrix",
    "--config", $Config,
    "--tasks", $Tasks,
    "--output", $Output
)
if ($ExtraArgs) {
    $cliArgs += $ExtraArgs
}

& agentbench @cliArgs
exit $LASTEXITCODE
