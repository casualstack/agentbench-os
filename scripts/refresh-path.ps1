# Refresh PATH in the current PowerShell session (run after winget installs gh).
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
if (Get-Command gh -ErrorAction SilentlyContinue) {
    gh --version
} else {
    Write-Host "gh still not found. Try: & 'C:\Program Files\GitHub CLI\gh.exe' --version"
}
