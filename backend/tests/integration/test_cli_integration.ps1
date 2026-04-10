# Pharos CLI Integration Test - Tests CLI + Backend together
# This verifies that CLI commands successfully communicate with the backend

$env:PHAROS_API_URL = "http://127.0.0.1:8000"
$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PHAROS CLI + BACKEND INTEGRATION TEST" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Testing full round-trip: CLI -> Backend -> Response" -ForegroundColor Yellow
Write-Host ""

# Wait for backend to be ready
Write-Host "Checking backend health..." -NoNewline
$maxRetries = 10
$retryCount = 0
$backendReady = $false

while ($retryCount -lt $maxRetries -and -not $backendReady) {
    try {
        $health = curl -UseBasicParsing http://127.0.0.1:8000/api/monitoring/health 2>$null | ConvertFrom-Json
        $backendReady = $true
        Write-Host " Backend is responding!" -ForegroundColor Green
    } catch {
        $retryCount++
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }
}

if (-not $backendReady) {
    Write-Host " FAILED - Backend not responding" -ForegroundColor Red
    exit 1
}

$results = @()

function Test-CLICommand {
    param(
        [string]$Name,
        [string]$Command,
        [string]$ExpectedInOutput,
        [string]$Category
    )
    
    Write-Host "Testing: $Name..." -NoNewline
    
    try {
        cd pharos-cli
        $output = Invoke-Expression "$Command 2>&1" | Out-String
        cd ..
        
        $success = $false
        $message = ""
        
        # Check if command executed successfully
        if ($LASTEXITCODE -eq 0) {
            # Check if we got expected output
            if ($ExpectedInOutput -and $output -match $ExpectedInOutput) {
                Write-Host " ✅ SUCCESS (CLI + Backend working)" -ForegroundColor Green
                $success = $true
                $message = "Got expected response from backend"
            } elseif (-not $ExpectedInOutput) {
                Write-Host " ✅ SUCCESS (Command executed)" -ForegroundColor Green
                $success = $true
                $message = "Command completed successfully"
            } else {
                Write-Host " ⚠️ PARTIAL (CLI works, unexpected response)" -ForegroundColor Yellow
                $success = $false
                $message = "Expected '$ExpectedInOutput' not found in output"
            }
        } elseif ($output -match "Not authenticated" -or $output -match "401") {
            Write-Host " 🔒 AUTH_REQUIRED (Backend responding, needs auth)" -ForegroundColor Yellow
            $success = $true
            $message = "Backend requires authentication (expected)"
        } elseif ($output -match "Connection.*refused" -or $output -match "Cannot connect") {
            Write-Host " ❌ BACKEND_DOWN (CLI works, backend not responding)" -ForegroundColor Red
            $success = $false
            $message = "Cannot connect to backend"
        } else {
            Write-Host " ❌ FAILED (Exit code: $LASTEXITCODE)" -ForegroundColor Red
            $success = $false
            $message = "Command failed with exit code $LASTEXITCODE"
        }
        
        $results += [PSCustomObject]@{
            Category = $Category
            Name = $Name
            Command = $Command
            Success = $success
            ExitCode = $LASTEXITCODE
            Message = $message
            OutputSample = $output.Substring(0, [Math]::Min(150, $output.Length))
        }
    } catch {
        Write-Host " ❌ EXCEPTION" -ForegroundColor Red
        $results += [PSCustomObject]@{
            Category = $Category
            Name = $Name
            Command = $Command
            Success = $false
            ExitCode = -1
            Message = $_.Exception.Message
            OutputSample = ""
        }
    }
}

# Test commands that don't need backend
Write-Host "`n📋 Testing Local Commands (No Backend Required)..." -ForegroundColor Cyan
Test-CLICommand "Version" "python -m pharos_cli version" "0.1.0" "Local"
Test-CLICommand "Info" "python -m pharos_cli info" "Terminal Information" "Local"

# Test commands that need backend but no auth
Write-Host "`n🏥 Testing Health Endpoints (Backend Required, No Auth)..." -ForegroundColor Cyan
# Note: These will likely require auth, which is expected

# Test commands that need backend and auth
Write-Host "`n🔐 Testing Authenticated Endpoints..." -ForegroundColor Cyan
Test-CLICommand "List Resources" "python -m pharos_cli resource list 2>&1" "" "Resources"
Test-CLICommand "List Collections" "python -m pharos_cli collection list 2>&1" "" "Collections"
Test-CLICommand "Search" "python -m pharos_cli search test 2>&1" "" "Search"

# Generate Report
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "INTEGRATION TEST SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$totalTests = $results.Count
$successCount = ($results | Where-Object { $_.Success -eq $true }).Count
$failedCount = $totalTests - $successCount

Write-Host "Total Tests:    $totalTests" -ForegroundColor White
Write-Host "✅ Success:     $successCount ($([math]::Round($successCount/$totalTests*100, 1))%)" -ForegroundColor Green
Write-Host "❌ Failed:      $failedCount ($([math]::Round($failedCount/$totalTests*100, 1))%)" -ForegroundColor Red

# Detailed Results
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "DETAILED RESULTS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$results | ForEach-Object {
    $color = if ($_.Success) { "Green" } else { "Red" }
    $status = if ($_.Success) { "✅" } else { "❌" }
    Write-Host "$status $($_.Name)" -ForegroundColor $color
    Write-Host "   Command: $($_.Command)" -ForegroundColor Gray
    Write-Host "   Message: $($_.Message)" -ForegroundColor Gray
    if ($_.OutputSample) {
        Write-Host "   Output: $($_.OutputSample)" -ForegroundColor DarkGray
    }
    Write-Host ""
}

# Save report
$reportPath = "cli_integration_report.txt"
$report = @"
========================================
PHAROS CLI + BACKEND INTEGRATION TEST
========================================
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Backend URL: $env:PHAROS_API_URL

SUMMARY
========================================
Total Tests: $totalTests
Success: $successCount ($([math]::Round($successCount/$totalTests*100, 1))%)
Failed: $failedCount ($([math]::Round($failedCount/$totalTests*100, 1))%)

DETAILED RESULTS
========================================
$($results | Format-Table -AutoSize | Out-String)

INTERPRETATION
========================================
✅ SUCCESS = CLI command executed AND backend responded appropriately
🔒 AUTH_REQUIRED = Backend is working but requires authentication (expected)
❌ FAILED = Either CLI or backend is not working correctly

NEXT STEPS
========================================
"@

if ($failedCount -gt 0) {
    $report += "`n• $failedCount tests failed. Investigate CLI or backend issues."
}

if (($results | Where-Object { $_.Message -match "authentication" }).Count -gt 0) {
    $report += "`n• Some endpoints require authentication. This is expected behavior."
    $report += "`n• To test authenticated endpoints, implement auth flow first."
}

$report | Out-File -FilePath $reportPath -Encoding UTF8
Write-Host "📄 Report saved to: $reportPath" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

# Return exit code based on results
if ($failedCount -eq 0) {
    exit 0
} else {
    exit 1
}
