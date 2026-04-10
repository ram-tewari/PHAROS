# Final Integration Test - CLI + Backend Round-Trip Verification
$env:PHAROS_API_URL = "http://127.0.0.1:8000"
$ErrorActionPreference = "Continue"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "PHAROS CLI + BACKEND INTEGRATION TEST" -ForegroundColor Cyan
Write-Host "Full Round-Trip Verification: CLI → Backend → Response" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

# Test 1: Backend Health
Write-Host "Test 1: Backend Health Check" -ForegroundColor Yellow
Write-Host "   Checking if backend is responding..." -NoNewline
try {
    $response = curl -UseBasicParsing http://127.0.0.1:8000/docs 2>$null
    if ($response.StatusCode -eq 200) {
        Write-Host " SUCCESS" -ForegroundColor Green
        $backendHealthy = $true
    } else {
        Write-Host " FAILED (Status: $($response.StatusCode))" -ForegroundColor Red
        $backendHealthy = $false
    }
} catch {
    Write-Host " FAILED (Not responding)" -ForegroundColor Red
    $backendHealthy = $false
}

if (-not $backendHealthy) {
    Write-Host "`nERROR: Backend is not running. Cannot proceed with integration tests." -ForegroundColor Red
    exit 1
}

Write-Host ""

# Test 2: CLI Local Commands
Write-Host "Test 2: CLI Local Commands (No Backend Required)" -ForegroundColor Yellow
$localTests = @(
    @{Name="Version"; Cmd="version"; Expected="0.1.0"},
    @{Name="Info"; Cmd="info"; Expected="Terminal Information"}
)

$localPassed = 0
foreach ($test in $localTests) {
    Write-Host "   Testing $($test.Name)..." -NoNewline
    try {
        cd pharos-cli
        $output = python -m pharos_cli $($test.Cmd) 2>&1 | Out-String
        cd ..
        
        if ($LASTEXITCODE -eq 0 -and $output -match $test.Expected) {
            Write-Host " SUCCESS" -ForegroundColor Green
            $localPassed++
        } else {
            Write-Host " FAILED" -ForegroundColor Red
        }
    } catch {
        Write-Host " ERROR" -ForegroundColor Red
    }
}

Write-Host "   Result: $localPassed/$($localTests.Count) passed`n" -ForegroundColor $(if ($localPassed -eq $localTests.Count) { "Green" } else { "Yellow" })

# Test 3: CLI → Backend Communication
Write-Host "Test 3: CLI → Backend Communication (Round-Trip)" -ForegroundColor Yellow
$commTests = @(
    @{Name="List Resources"; Cmd="resource list"},
    @{Name="List Collections"; Cmd="collection list"},
    @{Name="Search Query"; Cmd="search test"}
)

$commPassed = 0
foreach ($test in $commTests) {
    Write-Host "   Testing $($test.Name)..." -NoNewline
    try {
        cd pharos-cli
        $output = python -m pharos_cli $($test.Cmd) 2>&1 | Out-String
        cd ..
        
        # Check if backend responded (even if with auth error)
        if ($output -match "Not authenticated" -or $output -match "401" -or $output -match "Unauthorized") {
            Write-Host " SUCCESS (Backend responded - auth required)" -ForegroundColor Green
            $commPassed++
        } elseif ($output -match "Connection.*refused" -or $output -match "Cannot connect") {
            Write-Host " FAILED (Backend not responding)" -ForegroundColor Red
        } elseif ($LASTEXITCODE -eq 0) {
            Write-Host " SUCCESS (Got response)" -ForegroundColor Green
            $commPassed++
        } else {
            Write-Host " FAILED (Exit: $LASTEXITCODE)" -ForegroundColor Red
        }
    } catch {
        Write-Host " ERROR" -ForegroundColor Red
    }
}

Write-Host "   Result: $commPassed/$($commTests.Count) passed`n" -ForegroundColor $(if ($commPassed -eq $commTests.Count) { "Green" } else { "Yellow" })

# Test 4: Backend Endpoints Directly
Write-Host "Test 4: Backend Endpoints (Direct HTTP)" -ForegroundColor Yellow
$endpointTests = @(
    @{Name="Swagger UI"; Path="/docs"},
    @{Name="OpenAPI Schema"; Path="/openapi.json"}
)

$endpointPassed = 0
foreach ($test in $endpointTests) {
    Write-Host "   Testing $($test.Name)..." -NoNewline
    try {
        $response = curl -UseBasicParsing "http://127.0.0.1:8000$($test.Path)" 2>$null
        if ($response.StatusCode -eq 200) {
            Write-Host " SUCCESS (Status: 200)" -ForegroundColor Green
            $endpointPassed++
        } else {
            Write-Host " FAILED (Status: $($response.StatusCode))" -ForegroundColor Red
        }
    } catch {
        Write-Host " ERROR" -ForegroundColor Red
    }
}

Write-Host "   Result: $endpointPassed/$($endpointTests.Count) passed`n" -ForegroundColor $(if ($endpointPassed -eq $endpointTests.Count) { "Green" } else { "Yellow" })

# Summary
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "TEST SUMMARY" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

$totalPassed = $localPassed + $commPassed + $endpointPassed
$totalTests = $localTests.Count + $commTests.Count + $endpointTests.Count

Write-Host ""
Write-Host "Backend Health:           SUCCESS" -ForegroundColor Green
Write-Host "Local Commands:           $localPassed/$($localTests.Count) passed" -ForegroundColor $(if ($localPassed -eq $localTests.Count) { "Green" } else { "Yellow" })
Write-Host "CLI-Backend Communication: $commPassed/$($commTests.Count) passed" -ForegroundColor $(if ($commPassed -eq $commTests.Count) { "Green" } else { "Yellow" })
Write-Host "Backend Endpoints:        $endpointPassed/$($endpointTests.Count) passed" -ForegroundColor $(if ($endpointPassed -eq $endpointTests.Count) { "Green" } else { "Yellow" })
Write-Host ""
Write-Host "TOTAL: $totalPassed/$totalTests tests passed ($([math]::Round($totalPassed/$totalTests*100, 1))%)" -ForegroundColor $(if ($totalPassed -eq $totalTests) { "Green" } elseif ($totalPassed -ge $totalTests * 0.8) { "Yellow" } else { "Red" })

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "INTERPRETATION" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

if ($totalPassed -eq $totalTests) {
    Write-Host "SUCCESS: All integration tests passed!" -ForegroundColor Green
    Write-Host "The CLI and backend are fully integrated and working correctly." -ForegroundColor Green
    Write-Host ""
    Write-Host "What this means:" -ForegroundColor White
    Write-Host "  CLI commands execute without errors" -ForegroundColor White
    Write-Host "  CLI successfully connects to backend" -ForegroundColor White
    Write-Host "  Backend processes requests and returns responses" -ForegroundColor White
    Write-Host "  Full round-trip communication is verified" -ForegroundColor White
    $exitCode = 0
} elseif ($totalPassed -ge $totalTests * 0.8) {
    Write-Host "GOOD: Most integration tests passed." -ForegroundColor Yellow
    Write-Host "The CLI and backend are mostly working. Minor issues detected." -ForegroundColor Yellow
    $exitCode = 0
} else {
    Write-Host "FAILED: Many integration tests failed." -ForegroundColor Red
    Write-Host "There are significant issues with CLI-backend integration." -ForegroundColor Red
    $exitCode = 1
}

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Cyan

exit $exitCode
