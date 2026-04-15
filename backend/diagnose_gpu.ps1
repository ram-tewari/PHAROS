# GPU Diagnostic Script
# Run as Administrator to diagnose GPU/CUDA issues

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "GPU Diagnostic Tool" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: Must run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell -> Run as administrator" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[OK] Running as Administrator" -ForegroundColor Green
Write-Host ""

# Test 1: NVIDIA Driver
Write-Host "Test 1: NVIDIA Driver (nvidia-smi)" -ForegroundColor Yellow
try {
    $nvidiaSmi = nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] NVIDIA Driver detected:" -ForegroundColor Green
        Write-Host "     $nvidiaSmi" -ForegroundColor Gray
    } else {
        Write-Host "[FAIL] nvidia-smi failed" -ForegroundColor Red
        Write-Host "       Install NVIDIA drivers: https://www.nvidia.com/Download/index.aspx" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[FAIL] nvidia-smi not found" -ForegroundColor Red
    Write-Host "       Install NVIDIA drivers: https://www.nvidia.com/Download/index.aspx" -ForegroundColor Yellow
}
Write-Host ""

# Test 2: CUDA Toolkit
Write-Host "Test 2: CUDA Toolkit (nvcc)" -ForegroundColor Yellow
try {
    $nvccVersion = nvcc --version 2>&1 | Select-String "release"
    if ($nvccVersion) {
        Write-Host "[OK] CUDA Toolkit installed:" -ForegroundColor Green
        Write-Host "     $nvccVersion" -ForegroundColor Gray
    } else {
        Write-Host "[WARN] CUDA Toolkit not found" -ForegroundColor Yellow
        Write-Host "       PyTorch includes CUDA runtime, but full toolkit recommended" -ForegroundColor Gray
        Write-Host "       Download: https://developer.nvidia.com/cuda-11-8-0-download-archive" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] nvcc not found (CUDA Toolkit not installed)" -ForegroundColor Yellow
    Write-Host "       PyTorch includes CUDA runtime, but full toolkit recommended" -ForegroundColor Gray
}
Write-Host ""

# Test 3: PyTorch Installation
Write-Host "Test 3: PyTorch Installation" -ForegroundColor Yellow
try {
    $torchVersion = python -c "import torch; print(torch.__version__)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] PyTorch installed: $torchVersion" -ForegroundColor Green
        
        if ($torchVersion -like "*cu118*") {
            Write-Host "[OK] Built with CUDA 11.8 support" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] PyTorch not built with CUDA support" -ForegroundColor Red
            Write-Host "       Reinstall: pip install torch --index-url https://download.pytorch.org/whl/cu118" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[FAIL] PyTorch not installed" -ForegroundColor Red
        Write-Host "       Install: pip install -r requirements-edge.txt" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[FAIL] Python or PyTorch not found" -ForegroundColor Red
}
Write-Host ""

# Test 4: PyTorch CUDA Detection
Write-Host "Test 4: PyTorch CUDA Detection" -ForegroundColor Yellow
try {
    $cudaAvailable = python -c "import torch; print(torch.cuda.is_available())" 2>&1
    if ($cudaAvailable -eq "True") {
        Write-Host "[OK] CUDA is available to PyTorch!" -ForegroundColor Green
        
        $deviceName = python -c "import torch; print(torch.cuda.get_device_name(0))" 2>&1
        $deviceMemory = python -c "import torch; print(f'{torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}')" 2>&1
        
        Write-Host "     Device: $deviceName" -ForegroundColor Gray
        Write-Host "     Memory: $deviceMemory GB" -ForegroundColor Gray
    } else {
        Write-Host "[FAIL] CUDA not available to PyTorch" -ForegroundColor Red
        Write-Host ""
        Write-Host "Possible causes:" -ForegroundColor Yellow
        Write-Host "1. NVIDIA drivers not installed or outdated" -ForegroundColor Yellow
        Write-Host "2. CUDA runtime mismatch (PyTorch needs CUDA 11.8)" -ForegroundColor Yellow
        Write-Host "3. GPU not detected by system" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Solutions:" -ForegroundColor Yellow
        Write-Host "1. Update NVIDIA drivers: https://www.nvidia.com/Download/index.aspx" -ForegroundColor Yellow
        Write-Host "2. Install CUDA 11.8: https://developer.nvidia.com/cuda-11-8-0-download-archive" -ForegroundColor Yellow
        Write-Host "3. Restart computer after installation" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[FAIL] PyTorch CUDA check failed" -ForegroundColor Red
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$cudaWorks = python -c "import torch; print(torch.cuda.is_available())" 2>&1
if ($cudaWorks -eq "True") {
    Write-Host "[SUCCESS] GPU is ready for edge worker!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next step: Start the edge worker" -ForegroundColor Cyan
    Write-Host "   .\start_edge_worker.ps1" -ForegroundColor Gray
} else {
    Write-Host "[INCOMPLETE] GPU not available" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Edge worker will run on CPU (slower)" -ForegroundColor Yellow
    Write-Host "To enable GPU, follow the solutions above" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to exit"
