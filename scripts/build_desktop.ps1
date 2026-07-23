# Build the AgentBench desktop client (AgentBench.exe) with PyInstaller.
# Prereqs: pip install -e ".[app]" pyinstaller
$repo = Split-Path -Parent $PSScriptRoot

Push-Location $repo
try {
    # AgentBench.spec is the single source of truth for PyInstaller options
    # (icon, version resource, one-dir layout, upx) — CI builds the same way.
    # PyInstaller logs to stderr; run via cmd so PowerShell 5.1 does not
    # promote log lines to errors.
    cmd /c "python -m PyInstaller --noconfirm AgentBench.spec 2>&1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "PyInstaller failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host ""
    Write-Host "Built: $repo\dist\AgentBench\AgentBench.exe"
} finally {
    Pop-Location
}
