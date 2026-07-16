# Run API from backend folder (uses venv if present).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }

if (-not (Test-Path $py) -and $py -ne "python") {
    Write-Host "Create venv: python -m venv .venv" -ForegroundColor Red
    exit 1
}

& $py run_server.py @args
