# Pharos Edge Worker Startup Script
# Run this to start the edge worker with GPU support

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Administrator Privileges Required" -ForegroundColor Yellow
    Write-Host "Restarting with admin privileges..." -ForegroundColor Yellow
    $scriptPath = $MyInvocation.MyCommand.Path
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" -Verb RunAs
    exit
}

Write-Host "Pharos Edge Worker - Startup" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "ERROR: .env file not found!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Load environment
Write-Host "Loading environment..." -ForegroundColor Yellow
Get-Content .env | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

# Verify MODE
$mode = [Environment]::GetEnvironmentVariable("MODE", "Process")
if ($mode -ne "EDGE") {
    Write-Host "ERROR: MODE must be EDGE" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Environment loaded" -ForegroundColor Green
Write-Host ""

# Check PyTorch
Write-Host "Checking PyTorch..." -ForegroundColor Yellow
$torchCmd = 'import torch; print("PyTorch:", torch.__version__); print("CUDA:", torch.cuda.is_available())'
$torchCheck = python -c $torchCmd 2>&1
Write-Host $torchCheck -ForegroundColor Gray
Write-Host ""

# Start worker
Write-Host "Starting Edge Worker..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

try {
    python -m app.edge_worker
} catch {
    Write-Host "ERROR: Worker crashed!" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    Write-Host ""
    Write-Host "Edge Worker Stopped" -ForegroundColor Cyan
    Read-Host "Press Enter to exit"
}
