# Restart Pharos Edge Worker
# This script stops any running worker processes and starts a fresh one

Write-Host "=== Pharos Edge Worker Restart ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Stop any running worker processes
Write-Host "[1/4] Stopping existing worker processes..." -ForegroundColor Yellow
$workerProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*worker.py*" -or $_.CommandLine -like "*main_worker*"
}

if ($workerProcesses) {
    Write-Host "Found $($workerProcesses.Count) worker process(es), stopping..." -ForegroundColor Yellow
    $workerProcesses | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Host "Worker processes stopped" -ForegroundColor Green
} else {
    Write-Host "No running worker processes found" -ForegroundColor Gray
}

# Step 2: Verify environment
Write-Host ""
Write-Host "[2/4] Verifying environment..." -ForegroundColor Yellow

$requiredVars = @(
    "MODE",
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
    "DATABASE_URL",
    "PHAROS_ADMIN_TOKEN",
    "PHAROS_CLOUD_URL"
)

$missing = @()
foreach ($var in $requiredVars) {
    if (-not (Test-Path "env:$var")) {
        $missing += $var
    }
}

if ($missing.Count -gt 0) {
    Write-Host "ERROR: Missing environment variables:" -ForegroundColor Red
    foreach ($var in $missing) {
        Write-Host "  - $var" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "Please set these variables in backend/.env" -ForegroundColor Yellow
    exit 1
}

Write-Host "Environment OK" -ForegroundColor Green

# Step 3: Check if backend directory exists
Write-Host ""
Write-Host "[3/4] Checking backend directory..." -ForegroundColor Yellow

if (-not (Test-Path "backend")) {
    Write-Host "ERROR: backend directory not found" -ForegroundColor Red
    Write-Host "Please run this script from the pharos root directory" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path "backend/worker.py")) {
    Write-Host "ERROR: backend/worker.py not found" -ForegroundColor Red
    exit 1
}

Write-Host "Backend directory OK" -ForegroundColor Green

# Step 4: Start worker
Write-Host ""
Write-Host "[4/4] Starting edge worker..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Worker will run in this terminal window." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the worker." -ForegroundColor Cyan
Write-Host ""
Write-Host "Logs will appear below:" -ForegroundColor Gray
Write-Host "================================================================" -ForegroundColor Gray
Write-Host ""

# Change to backend directory and start worker
Set-Location backend
python worker.py
