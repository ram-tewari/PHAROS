# Pharos Edge Worker Launcher (PowerShell)
#
# Loads configuration from backend/.env (never hard-code credentials here)
# and starts the unified edge worker. Copy config/.env.edge.template to
# backend/.env and fill in your own values first.

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Pharos Unified Edge Worker" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "  Missing $envFile - copy config/.env.edge.template and fill it in." -ForegroundColor Red
    exit 1
}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"'), "Process")
    }
}

$env:MODE = "EDGE"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "  Mode             : EDGE" -ForegroundColor Green
Write-Host "  Queues (BLPOP)   : pharos:tasks, ingest_queue" -ForegroundColor Green
Write-Host "  Working dir      : $(Get-Location)" -ForegroundColor Green
Write-Host "  Python           : $(python --version 2>&1)" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Start the worker via worker.py — it patches platform.uname before any
# app import so Python 3.13 + Windows WMI doesn't hang.
python worker.py
