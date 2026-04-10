# Simple Integration Test - CLI + Backend
$env:PHAROS_API_URL = "http://127.0.0.1:8000"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CLI + BACKEND INTEGRATION TEST" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Check backend
Write-Host "1. Checking backend..." -NoNewline
try {
    $health = curl -UseBasicParsing http://127.0.0.1:8000/docs 2>$null
    Write-Host " ✅ Backend responding" -ForegroundColor Green
} catch {
    Write-Host " ❌ Backend not responding" -ForegroundColor Red
    exit 1
}

# Test CLI commands
Write-Host "`n2. Testing CLI Commands:`n" -ForegroundColor Cyan

$tests = @(
    @{Name="Version (local)"; Cmd="python -m pharos_cli version"; NeedsBackend=$false},
    @{Name="Info (local)"; Cmd="python -m pharos_cli info"; NeedsBackend=$false}
)

$success = 0
$total = 0

foreach ($test in $tests) {
    $total++
    Write-Host "   Testing: $($test.Name)..." -NoNewline
    
    try {
        cd pharos-cli
        $output = Invoke-Expression "$($test.Cmd) 2>&1" | Out-String
        cd ..
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host " ✅" -ForegroundColor Green
            $success++
        } else {
            Write-Host " ❌ (Exit: $LASTEXITCODE)" -ForegroundColor Red
        }
    } catch {
        Write-Host " ❌ ERROR" -ForegroundColor Red
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "RESULTS: $success/$total tests passed" -ForegroundColor $(if ($success -eq $total) { "Green" } else { "Yellow" })
Write-Host "========================================`n" -ForegroundColor Cyan
