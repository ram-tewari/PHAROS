# Pharos Edge Worker Startup Script (PowerShell)
# This script starts the edge worker with proper environment configuration

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Pharos Edge Worker - Startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env.edge exists
if (-not (Test-Path ".env.edge")) {
    Write-Host "ERROR: .env.edge file not found!" -ForegroundColor Red
    Write-Host "Please copy .env.edge to configure the edge worker." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Load environment from .env.edge
Write-Host "Loading environment from .env.edge..." -ForegroundColor Yellow
Get-Content .env.edge | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
        Write-Host "  Set $name" -ForegroundColor Gray
    }
}

# Verify MODE is set to EDGE
$mode = [Environment]::GetEnvironmentVariable("MODE", "Process")
if ($mode -ne "EDGE") {
    Write-Host "ERROR: MODE must be set to EDGE in .env.edge" -ForegroundColor Red
    Write-Host "Current MODE: $mode" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "✓ Environment loaded" -ForegroundColor Green
Write-Host ""

# Check if virtual environment is activated
$venvActive = $env:VIRTUAL_ENV -ne $null
if (-not $venvActive) {
    Write-Host "WARNING: Virtual environment not activated" -ForegroundColor Yellow
    Write-Host "Activate with: .venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host ""
}

# Check if PyTorch is installed
Write-Host "Checking PyTorch installation..." -ForegroundColor Yellow
try {
    $torchCheck = python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA Available:', torch.cuda.is_available())" 2>&1
    Write-Host $torchCheck -ForegroundColor Gray
} catch {
    Write-Host "ERROR: PyTorch not installed!" -ForegroundColor Red
    Write-Host "Install with: pip install -r requirements-edge.txt" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# Check if sentence-transformers is installed
Write-Host "Checking sentence-transformers installation..." -ForegroundColor Yellow
try {
    $stCheck = python -c "import sentence_transformers; print('sentence-transformers:', sentence_transformers.__version__)" 2>&1
    Write-Host $stCheck -ForegroundColor Gray
} catch {
    Write-Host "ERROR: sentence-transformers not installed!" -ForegroundColor Red
    Write-Host "Install with: pip install -r requirements-edge.txt" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# Start edge worker
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Edge Worker..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

try {
    python -m app.edge_worker
} catch {
    Write-Host ""
    Write-Host "ERROR: Edge worker crashed!" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Edge Worker Stopped" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Read-Host "Press Enter to exit"
}
