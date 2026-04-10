# Pharos CLI Endpoint Testing Script
# Tests all CLI commands against the local backend

$env:PHAROS_API_URL = "http://127.0.0.1:8000"
$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PHAROS CLI ENDPOINT TEST" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Base URL: $env:PHAROS_API_URL" -ForegroundColor Yellow
Write-Host "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host ""

$results = @()

function Test-Command {
    param(
        [string]$Name,
        [string]$Command,
        [string]$Category
    )
    
    Write-Host "Testing: $Name..." -NoNewline
    
    try {
        $output = Invoke-Expression "cd pharos-cli; $Command 2>&1" | Out-String
        $exitCode = $LASTEXITCODE
        
        if ($exitCode -eq 0) {
            Write-Host " ✅ SUCCESS" -ForegroundColor Green
            $status = "✅ SUCCESS"
        } elseif ($output -match "Not authenticated" -or $output -match "401") {
            Write-Host " 🔒 AUTH_REQUIRED" -ForegroundColor Yellow
            $status = "🔒 AUTH_REQUIRED"
        } elseif ($output -match "No such command" -or $output -match "Usage:") {
            Write-Host " ❌ NOT_IMPLEMENTED" -ForegroundColor Red
            $status = "❌ NOT_IMPLEMENTED"
        } else {
            Write-Host " ⚠️ ERROR" -ForegroundColor Magenta
            $status = "⚠️ ERROR"
        }
        
        $results += [PSCustomObject]@{
            Category = $Category
            Name = $Name
            Command = $Command
            Status = $status
            ExitCode = $exitCode
            Output = $output.Substring(0, [Math]::Min(200, $output.Length))
        }
    } catch {
        Write-Host " ❌ EXCEPTION" -ForegroundColor Red
        $results += [PSCustomObject]@{
            Category = $Category
            Name = $Name
            Command = $Command
            Status = "❌ EXCEPTION"
            ExitCode = -1
            Output = $_.Exception.Message
        }
    }
}

# Test Basic Commands
Write-Host "`n📋 Testing Basic Commands..." -ForegroundColor Cyan
Test-Command "Version" "python -m pharos_cli version" "Basic"
Test-Command "Info" "python -m pharos_cli info" "Basic"

# Test System Commands
Write-Host "`n🖥️ Testing System Commands..." -ForegroundColor Cyan
Test-Command "System Help" "python -m pharos_cli system --help" "System"

# Test Resource Commands
Write-Host "`n📚 Testing Resource Commands..." -ForegroundColor Cyan
Test-Command "Resource Help" "python -m pharos_cli resource --help" "Resource"

# Test Collection Commands
Write-Host "`n📁 Testing Collection Commands..." -ForegroundColor Cyan
Test-Command "Collection Help" "python -m pharos_cli collection --help" "Collection"

# Test Search Commands
Write-Host "`n🔍 Testing Search Commands..." -ForegroundColor Cyan
Test-Command "Search Help" "python -m pharos_cli search --help" "Search"

# Test Annotation Commands
Write-Host "`n📝 Testing Annotation Commands..." -ForegroundColor Cyan
Test-Command "Annotate Help" "python -m pharos_cli annotate --help" "Annotation"

# Test Quality Commands
Write-Host "`n⭐ Testing Quality Commands..." -ForegroundColor Cyan
Test-Command "Quality Help" "python -m pharos_cli quality --help" "Quality"

# Test Taxonomy Commands
Write-Host "`n🏷️ Testing Taxonomy Commands..." -ForegroundColor Cyan
Test-Command "Taxonomy Help" "python -m pharos_cli taxonomy --help" "Taxonomy"

# Test Graph Commands
Write-Host "`n🕸️ Testing Graph Commands..." -ForegroundColor Cyan
Test-Command "Graph Help" "python -m pharos_cli graph --help" "Graph"

# Test Recommendation Commands
Write-Host "`n💡 Testing Recommendation Commands..." -ForegroundColor Cyan
Test-Command "Recommend Help" "python -m pharos_cli recommend --help" "Recommendation"

# Test Code Commands
Write-Host "`n💻 Testing Code Commands..." -ForegroundColor Cyan
Test-Command "Code Help" "python -m pharos_cli code --help" "Code"

# Test RAG Commands
Write-Host "`n🤖 Testing RAG Commands..." -ForegroundColor Cyan
Test-Command "Ask Help" "python -m pharos_cli ask --help" "RAG"

# Test Chat Commands
Write-Host "`n💬 Testing Chat Commands..." -ForegroundColor Cyan
Test-Command "Chat Help" "python -m pharos_cli chat --help" "Chat"

# Test Batch Commands
Write-Host "`n📦 Testing Batch Commands..." -ForegroundColor Cyan
Test-Command "Batch Help" "python -m pharos_cli batch --help" "Batch"

# Test Backup Commands
Write-Host "`n💾 Testing Backup Commands..." -ForegroundColor Cyan
Test-Command "Backup Help" "python -m pharos_cli backup --help" "Backup"

# Test Auth Commands
Write-Host "`n🔐 Testing Auth Commands..." -ForegroundColor Cyan
Test-Command "Auth Help" "python -m pharos_cli auth --help" "Auth"

# Test Config Commands
Write-Host "`n⚙️ Testing Config Commands..." -ForegroundColor Cyan
Test-Command "Config Help" "python -m pharos_cli config --help" "Config"

# Generate Report
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "TEST SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$totalTests = $results.Count
$successCount = ($results | Where-Object { $_.Status -eq "✅ SUCCESS" }).Count
$authCount = ($results | Where-Object { $_.Status -eq "🔒 AUTH_REQUIRED" }).Count
$errorCount = ($results | Where-Object { $_.Status -like "*ERROR*" }).Count
$notImplemented = ($results | Where-Object { $_.Status -eq "❌ NOT_IMPLEMENTED" }).Count

Write-Host "Total Tests:        $totalTests" -ForegroundColor White
Write-Host "✅ Success:         $successCount ($([math]::Round($successCount/$totalTests*100, 1))%%)" -ForegroundColor Green
Write-Host "🔒 Auth Required:   $authCount ($([math]::Round($authCount/$totalTests*100, 1))%%)" -ForegroundColor Yellow
Write-Host "❌ Errors:          $errorCount ($([math]::Round($errorCount/$totalTests*100, 1))%%)" -ForegroundColor Red
Write-Host "❌ Not Implemented: $notImplemented ($([math]::Round($notImplemented/$totalTests*100, 1))%%)" -ForegroundColor Red

$workingPercentage = ($successCount + $authCount) / $totalTests * 100
Write-Host "`nOverall Health: $([math]::Round($workingPercentage, 1))%%" -ForegroundColor $(if ($workingPercentage -ge 90) { "Green" } elseif ($workingPercentage -ge 75) { "Yellow" } else { "Red" })

# Detailed Results by Category
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "DETAILED RESULTS BY CATEGORY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$results | Group-Object Category | ForEach-Object {
    Write-Host "`n$($_.Name):" -ForegroundColor Cyan
    $_.Group | ForEach-Object {
        Write-Host "  $($_.Status) $($_.Name)" -ForegroundColor $(
            switch -Wildcard ($_.Status) {
                "*SUCCESS*" { "Green" }
                "*AUTH*" { "Yellow" }
                "*ERROR*" { "Red" }
                "*NOT_IMPLEMENTED*" { "Magenta" }
                default { "White" }
            }
        )
    }
}

# Save detailed report
$reportPath = "cli_test_report.txt"
$report = @"
========================================
PHAROS CLI ENDPOINT TEST REPORT
========================================
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Base URL: $env:PHAROS_API_URL
Total Commands Tested: $totalTests

SUMMARY
========================================
✅ Success:         $successCount ($([math]::Round($successCount/$totalTests*100, 1))%%)
🔒 Auth Required:   $authCount ($([math]::Round($authCount/$totalTests*100, 1))%%)
❌ Errors:          $errorCount ($([math]::Round($errorCount/$totalTests*100, 1))%%)
❌ Not Implemented: $notImplemented ($([math]::Round($notImplemented/$totalTests*100, 1))%%)

Overall Health: $([math]::Round($workingPercentage, 1))%%

DETAILED RESULTS
========================================
$($results | Format-Table -AutoSize | Out-String)

RECOMMENDATIONS
========================================
"@

if ($authCount -gt 0) {
    $report += "`n• $authCount commands require authentication. Implement auth flow to test fully."
}

if ($errorCount -gt 0) {
    $report += "`n• $errorCount commands have errors. These need investigation."
}

if ($notImplemented -gt 0) {
    $report += "`n• $notImplemented commands are not implemented. Check CLI structure."
}

$report | Out-File -FilePath $reportPath -Encoding UTF8
Write-Host "`n📄 Detailed report saved to: $reportPath" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan
