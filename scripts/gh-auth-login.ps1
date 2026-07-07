# Opens GitHub CLI web login in this window.
$Gh = "C:\Program Files\GitHub CLI\gh.exe"

Write-Host ""
Write-Host "=== GitHub CLI login ===" -ForegroundColor Cyan
Write-Host "A browser window should open. Complete login there, then return here." -ForegroundColor Gray
Write-Host ""

if (-not (Test-Path -LiteralPath $Gh)) {
    Write-Host "gh not found at: $Gh" -ForegroundColor Red
    Write-Host "Install: winget install --id GitHub.cli" -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}

& $Gh auth login --hostname github.com --git-protocol https --web

Write-Host ""
& $Gh auth status
Write-Host ""
Read-Host "Press Enter to close this window"
