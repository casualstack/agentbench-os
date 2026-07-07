# Copy an AgentBench gate workflow into a target repository.
#
# Usage:
#   .\scripts\dogfood_setup.ps1 -TargetRepo C:\path\to\repo [-Template python|infra-k8s]

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $TargetRepo,

    [ValidateSet("python", "infra-k8s")]
    [string] $Template = "python"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

$TargetRepo = (Resolve-Path -LiteralPath $TargetRepo).Path

$templateMap = @{
    "python"         = Join-Path $RepoRoot "examples\dogfood\generic-python-repo-workflow.yml"
    "infra-k8s" = Join-Path $RepoRoot "examples\dogfood\infra-k8s-workflow.yml"
}

$Src = $templateMap[$Template]
if (-not (Test-Path -LiteralPath $Src)) {
    throw "Template not found: $Src"
}

$DestDir = Join-Path $TargetRepo ".github\workflows"
$DestFile = Join-Path $DestDir "agentbench-gate.yml"
$AgentbenchDir = Join-Path $TargetRepo ".agentbench"
$TasksDir = Join-Path $AgentbenchDir "tasks"

New-Item -ItemType Directory -Force -Path $DestDir, $TasksDir | Out-Null
Copy-Item -LiteralPath $Src -Destination $DestFile -Force
New-Item -ItemType File -Force -Path (Join-Path $AgentbenchDir ".gitkeep") | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $TasksDir ".gitkeep") | Out-Null

Write-Host @"
AgentBench gate workflow installed.

  Workflow: $DestFile
  Trajectory dir: $AgentbenchDir\
  Tasks dir: $TasksDir\

Next steps:
  1. Add .agentbench\last-run.json (recorded agent trajectory)
  2. Optionally copy task JSON from $RepoRoot\tasks\ into $TasksDir\
  3. Commit and open a PR — see docs\GITHUB_ACTION.md
"@
