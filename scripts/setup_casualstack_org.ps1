# Create the Casualstack GitHub org and push the org profile repo (casualstack/.github).
#
# Does NOT create or push product repos (agentbench-os, witness, k8sattest).
#
# Usage:
#   .\scripts\setup_casualstack_org.ps1
#   .\scripts\setup_casualstack_org.ps1 -ProfileRepoPath C:\path\to\casualstack-github-org

[CmdletBinding()]
param(
    [string] $ProfileRepoPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProfileRepoPath) {
    $scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $agentBenchRoot = Split-Path -Parent $scriptDir
    $ProfileRepoPath = Join-Path (Split-Path -Parent $agentBenchRoot) "casualstack-github-org"
}
$OrgName = "casualstack"
$OrgDescription = "Execution accountability for AI agents"
$ProfileRepo = "$OrgName/.github"
$script:GhExe = $null

function Resolve-GhCli {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd) {
        $script:GhExe = $cmd.Source
        return
    }

    $candidates = @(
        "C:\Program Files\GitHub CLI\gh.exe",
        "C:\Program Files (x86)\GitHub CLI\gh.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path -LiteralPath $path) {
            $dir = Split-Path -Parent $path
            $env:Path = "$dir;$env:Path"
            $script:GhExe = $path
            Write-Host "Using gh at: $path" -ForegroundColor DarkGray
            return
        }
    }

    Write-Host "GitHub CLI (gh) is not installed." -ForegroundColor Yellow
    Write-Host "Install with: winget install --id GitHub.cli" -ForegroundColor Cyan
    Write-Host "Then close and reopen PowerShell, or run:" -ForegroundColor Cyan
    Write-Host '  $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")' -ForegroundColor Cyan
    throw "gh CLI required."
}

function Invoke-Gh {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]] $Args)
    & $script:GhExe @Args
    return $LASTEXITCODE
}

function Ensure-GhAuth {
    $null = Invoke-Gh auth status
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Authenticate with: gh auth login" -ForegroundColor Cyan
        throw "gh is not authenticated. Run: gh auth login"
    }
    Write-Host "gh auth: OK"
}

function Ensure-Org {
    param([string] $Name, [string] $Description)

    $null = Invoke-Gh api "orgs/$Name"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Organization '$Name' already exists - skipping creation."
        return
    }

    Write-Host "Creating organization '$Name'..."
    $null = Invoke-Gh org create $Name --description $Description
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create organization '$Name'. The slug may be taken or your account may lack org-creation permissions."
    }
    Write-Host "Organization '$Name' created."
}

function Ensure-ProfileRepo {
    param(
        [string] $LocalPath,
        [string] $RemoteRepo
    )

    if (-not (Test-Path -LiteralPath (Join-Path $LocalPath "profile\README.md"))) {
        throw "Profile README not found at $LocalPath\profile\README.md"
    }

    $LocalPath = (Resolve-Path -LiteralPath $LocalPath).Path

    if (-not (Test-Path -LiteralPath (Join-Path $LocalPath ".git"))) {
        Write-Host "Initializing git in $LocalPath..."
        Push-Location $LocalPath
        try {
            git init
            git branch -M main
            git add profile/ CODE_OF_CONDUCT.md SECURITY.md
            if (git status --porcelain) {
                git commit -m "Add Casualstack org profile (coming soon)"
            }
        } finally {
            Pop-Location
        }
    }

    $null = Invoke-Gh repo view $RemoteRepo
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Remote repo '$RemoteRepo' already exists."
        Push-Location $LocalPath
        try {
            $remotes = git remote
            if ($remotes -notcontains "origin") {
                git remote add origin "https://github.com/$RemoteRepo.git"
            }
            git push -u origin main
        } finally {
            Pop-Location
        }
        return
    }

    Write-Host "Creating and pushing '$RemoteRepo'..."
    Push-Location $LocalPath
    try {
        $null = Invoke-Gh repo create $RemoteRepo --public --source=. --remote=origin --push --description "Casualstack organization profile"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create remote repo '$RemoteRepo'."
        }
    } finally {
        Pop-Location
    }
}

Write-Host "=== Casualstack GitHub org setup ===" -ForegroundColor Green
Write-Host "Profile source: $ProfileRepoPath"
Write-Host ""

Resolve-GhCli
Ensure-GhAuth
Ensure-Org -Name $OrgName -Description $OrgDescription
Ensure-ProfileRepo -LocalPath $ProfileRepoPath -RemoteRepo $ProfileRepo

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host ""
Write-Host "Org profile:  https://github.com/$OrgName"
Write-Host "Profile repo: https://github.com/$ProfileRepo"
Write-Host ""
Write-Host "Next steps (manual):"
Write-Host "  1. Org settings - require 2FA for all members"
Write-Host "  2. Org settings - base permissions: No permission (or Read)"
Write-Host "  3. Org settings - Actions: allow selected or all (per policy)"
Write-Host "  4. See docs\GITHUB_ORG_RUNBOOK.md for branch protection when product repos go public"
Write-Host ""
Write-Host "NOT pushed (by design):"
Write-Host "  - casualstack/agentbench-os"
Write-Host "  - casualstack/witness"
Write-Host "  - casualstack/k8sattest"
Write-Host ""
Write-Host 'Remove "coming soon" from profile/README.md before publishing product repos.'
