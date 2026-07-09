# Build the AgentBench desktop client (AgentBench.exe) with PyInstaller.
# Prereqs: pip install -e ".[app]" pyinstaller
$repo = Split-Path -Parent $PSScriptRoot

Push-Location $repo
try {
    # PyInstaller logs to stderr; run via cmd so PowerShell 5.1 does not
    # promote log lines to errors.
    cmd /c "python -m PyInstaller --noconfirm --onefile --windowed --name AgentBench --icon src\agentbench\ui\static\agentbench-logo.ico --collect-data agentbench --collect-all webview scripts\desktop_entry.py 2>&1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "PyInstaller failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host ""
    Write-Host "Built: $repo\dist\AgentBench.exe"
} finally {
    Pop-Location
}
