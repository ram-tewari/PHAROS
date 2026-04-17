# Comprehensive API Endpoint Testing Script
# Tests all major endpoint categories rigorously

param(
    [string]$ApiUrl = "https://pharos-cloud-api.onrender.com"
)

$ErrorActionPreference = "Continue"
$headers = @{
    "Content-Type" = "application/json"
    "Origin" = $ApiUrl
}

# Test results tracking
$script:totalTests = 0
$script:passedTests = 0
$script:failedTests = 0
$script:testResults = @()

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [int[]]$ExpectedStatusCodes = @(200, 201)
    )
    
    $script:totalTests++
    $url = "$ApiUrl$Path"
    
    Write-Host "`n[$script:totalTests] Testing: $Name" -ForegroundColor Cyan
    Write-Host "   $Method $Path" -ForegroundColor Gray
    
    try {
        $params = @{
            Uri = $url
            Method = $Method
            Headers = $headers
            TimeoutSec = 30
        }
        
        if ($Body) {
            $params.Body = ($Body | ConvertTo-Json -Depth 10)
            Write-Host "   Body: $($params.Body.Substring(0, [Math]::Min(100, $params.Body.Length)))..." -ForegroundColor Gray
        }
        
        $response = Invoke-RestMethod @params
        
        # Success - assume 200/201
        Write-Host "   ✅ PASS (Status: 200)" -ForegroundColor Green
        $script:passedTests++
        $script:testResults += [PSCustomObject]@{
            Test = $Name
            Status = "PASS"
            StatusCode = 200
            Method = $Method
            Path = $Path
        }
        return $response
    } catch {
        $statusCode = 0
        $errorMessage = $_.Exception.Message
        
        # Try to extract status code
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        
        # Check if this is an expected status code
        if ($statusCode -in $ExpectedStatusCodes) {
            Write-Host "   ✅ PASS (Status: $statusCode)" -ForegroundColor Green
            $script:passedTests++
            $script:testResults += [PSCustomObject]@{
                Test = $Name
                Status = "PASS"
                StatusCode = $statusCode
                Method = $Method
                Path = $Path
            }
        } else {
            Write-Host "   ❌ FAIL (Status: $statusCode): $errorMessage" -ForegroundColor Red
            $script:failedTests++
            $script:testResults += [PSCustomObject]@{
                Test = $Name
                Status = "FAIL"
                StatusCode = $statusCode
                Method = $Method
                Path = $Path
                Error = $errorMessage
            }
        }
        return $null
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Pharos API - Comprehensive Endpoint Testing" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "API URL: $ApiUrl" -ForegroundColor White
Write-Host ""

# ============================================================
# CATEGORY 1: HEALTH & MONITORING
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 1: HEALTH & MONITORING" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

Test-Endpoint -Name "Root Health Check" -Method GET -Path "/health"
Test-Endpoint -Name "Monitoring Health" -Method GET -Path "/api/monitoring/health"
Test-Endpoint -Name "Database Health" -Method GET -Path "/api/monitoring/database"
Test-Endpoint -Name "ML Model Health" -Method GET -Path "/api/monitoring/health/ml"
Test-Endpoint -Name "Cache Stats" -Method GET -Path "/api/monitoring/cache/stats"
Test-Endpoint -Name "DB Pool Stats" -Method GET -Path "/api/monitoring/db/pool"
Test-Endpoint -Name "Performance Metrics" -Method GET -Path "/api/monitoring/performance"
Test-Endpoint -Name "Worker Status" -Method GET -Path "/api/monitoring/workers/status"

# ============================================================
# CATEGORY 2: RESOURCES (CRUD)
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 2: RESOURCES (CRUD)" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

# Create resource
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$guid = [guid]::NewGuid().ToString().Substring(0,8)
$createPayload = @{
    url = "https://github.com/test/repo-$guid"
    title = "Test Resource - $timestamp"
    resource_type = "code_repository"
    description = "Comprehensive endpoint test resource"
}

$resource = Test-Endpoint -Name "Create Resource" -Method POST -Path "/api/resources" -Body $createPayload -ExpectedStatusCodes @(200, 201)
$resourceId = $resource.id

if ($resourceId) {
    Write-Host "   Created Resource ID: $resourceId" -ForegroundColor Gray
    
    # Wait for processing
    Start-Sleep -Seconds 3
    
    # Get resource
    Test-Endpoint -Name "Get Resource by ID" -Method GET -Path "/api/resources/$resourceId"
    
    # Get resource status
    Test-Endpoint -Name "Get Resource Status" -Method GET -Path "/api/resources/$resourceId/status"
    
    # Get resource chunks
    Test-Endpoint -Name "Get Resource Chunks" -Method GET -Path "/api/resources/$resourceId/chunks"
    
    # Update resource
    $updatePayload = @{
        title = "Updated Test Resource - $timestamp"
        description = "Updated description"
    }
    Test-Endpoint -Name "Update Resource" -Method PUT -Path "/api/resources/$resourceId" -Body $updatePayload
}

# List resources
Test-Endpoint -Name "List Resources" -Method GET -Path "/api/resources"
Test-Endpoint -Name "Resources Health" -Method GET -Path "/api/resources/health"

# ============================================================
# CATEGORY 3: SEARCH
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 3: SEARCH" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

$searchPayload = @{
    query = "authentication"
    limit = 10
}

Test-Endpoint -Name "Basic Search" -Method POST -Path "/api/search/search" -Body $searchPayload
Test-Endpoint -Name "Advanced Search" -Method POST -Path "/api/search/advanced" -Body $searchPayload
Test-Endpoint -Name "Search Health" -Method GET -Path "/api/search/search/health"

# ============================================================
# CATEGORY 4: COLLECTIONS
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 4: COLLECTIONS" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

# Create collection
$collectionPayload = @{
    name = "Test Collection - $timestamp"
    description = "Test collection for endpoint testing"
    visibility = "private"
}

$collection = Test-Endpoint -Name "Create Collection" -Method POST -Path "/api/collections" -Body $collectionPayload -ExpectedStatusCodes @(200, 201)
$collectionId = $collection.id

if ($collectionId) {
    Write-Host "   Created Collection ID: $collectionId" -ForegroundColor Gray
    
    # Get collection
    Test-Endpoint -Name "Get Collection by ID" -Method GET -Path "/api/collections/$collectionId"
    
    # Add resource to collection (if we have a resource)
    if ($resourceId) {
        Test-Endpoint -Name "Add Resource to Collection" -Method POST -Path "/api/collections/$collectionId/resources/$resourceId"
        Test-Endpoint -Name "Get Collection Resources" -Method GET -Path "/api/collections/$collectionId/resources"
    }
    
    # Update collection
    $updateCollectionPayload = @{
        name = "Updated Test Collection - $timestamp"
    }
    Test-Endpoint -Name "Update Collection" -Method PUT -Path "/api/collections/$collectionId" -Body $updateCollectionPayload
}

# List collections
Test-Endpoint -Name "List Collections" -Method GET -Path "/api/collections"
Test-Endpoint -Name "Collections Health" -Method GET -Path "/api/collections/health"

# ============================================================
# CATEGORY 5: ANNOTATIONS
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 5: ANNOTATIONS" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

if ($resourceId) {
    # Create annotation
    $annotationPayload = @{
        resource_id = $resourceId
        annotation_type = "note"
        content = "Test annotation for endpoint testing"
        tags = @("test", "endpoint")
    }
    
    $annotation = Test-Endpoint -Name "Create Annotation" -Method POST -Path "/api/annotations/annotations" -Body $annotationPayload -ExpectedStatusCodes @(200, 201)
    $annotationId = $annotation.id
    
    if ($annotationId) {
        Write-Host "   Created Annotation ID: $annotationId" -ForegroundColor Gray
        
        # Get annotation
        Test-Endpoint -Name "Get Annotation by ID" -Method GET -Path "/api/annotations/annotations/$annotationId"
        
        # Get resource annotations
        Test-Endpoint -Name "Get Resource Annotations" -Method GET -Path "/api/annotations/resources/$resourceId/annotations"
        
        # Search annotations by tags
        $tagSearchPayload = @{
            tags = @("test")
        }
        Test-Endpoint -Name "Search Annotations by Tags" -Method POST -Path "/api/annotations/annotations/search/tags" -Body $tagSearchPayload
    }
}

# ============================================================
# CATEGORY 6: QUALITY
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 6: QUALITY" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

Test-Endpoint -Name "Quality Health" -Method GET -Path "/api/quality/quality/health"
Test-Endpoint -Name "Quality Dimensions" -Method GET -Path "/api/quality/quality/dimensions"
Test-Endpoint -Name "Quality Distribution" -Method GET -Path "/api/quality/quality/distribution"
Test-Endpoint -Name "Quality Outliers" -Method GET -Path "/api/quality/quality/outliers"
Test-Endpoint -Name "Quality Trends" -Method GET -Path "/api/quality/quality/trends"

if ($resourceId) {
    Test-Endpoint -Name "Get Resource Quality Details" -Method GET -Path "/api/quality/resources/$resourceId/quality-details"
}

# ============================================================
# CATEGORY 7: GRAPH & KNOWLEDGE
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 7: GRAPH & KNOWLEDGE" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

Test-Endpoint -Name "Graph Overview" -Method GET -Path "/api/graph/overview"
Test-Endpoint -Name "Graph Layout" -Method GET -Path "/api/graph/layout"
Test-Endpoint -Name "Graph Communities" -Method GET -Path "/api/graph/communities"
Test-Endpoint -Name "Graph Centrality" -Method GET -Path "/api/graph/centrality"
Test-Endpoint -Name "Graph Entities" -Method GET -Path "/api/graph/entities"

if ($resourceId) {
    Test-Endpoint -Name "Get Resource Neighbors" -Method GET -Path "/api/graph/resource/$resourceId/neighbors"
}

# ============================================================
# CATEGORY 8: SCHOLARLY
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 8: SCHOLARLY" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

Test-Endpoint -Name "Scholarly Health" -Method GET -Path "/api/scholarly/health"
Test-Endpoint -Name "Metadata Completeness Stats" -Method GET -Path "/api/scholarly/metadata/completeness-stats"

if ($resourceId) {
    Test-Endpoint -Name "Get Resource Metadata" -Method GET -Path "/api/scholarly/resources/$resourceId/metadata"
    Test-Endpoint -Name "Get Resource Equations" -Method GET -Path "/api/scholarly/resources/$resourceId/equations"
    Test-Endpoint -Name "Get Resource Tables" -Method GET -Path "/api/scholarly/resources/$resourceId/tables"
}

# ============================================================
# CATEGORY 9: PATTERNS (NEW)
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 9: PATTERNS" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

Test-Endpoint -Name "List Pattern Profiles" -Method GET -Path "/api/patterns/profiles"
Test-Endpoint -Name "Get Coding Profile" -Method GET -Path "/api/patterns/profiles/coding"
Test-Endpoint -Name "List Pattern Rules" -Method GET -Path "/api/patterns/rules"

# ============================================================
# CATEGORY 10: PDF INGESTION (PHASE 4)
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 10: PDF INGESTION" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

# Note: PDF upload requires multipart/form-data, skipping for now
Write-Host "   ⚠️  PDF upload requires file upload (multipart/form-data)" -ForegroundColor Yellow
Write-Host "   ⚠️  Skipping PDF ingest test" -ForegroundColor Yellow

# ============================================================
# CATEGORY 11: MCP INTEGRATION
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CATEGORY 11: MCP INTEGRATION" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

Test-Endpoint -Name "List MCP Tools" -Method GET -Path "/api/v1/mcp/tools"
Test-Endpoint -Name "List MCP Sessions" -Method GET -Path "/api/v1/mcp/sessions"

# ============================================================
# CLEANUP
# ============================================================
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "CLEANUP" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

if ($annotationId) {
    Test-Endpoint -Name "Delete Annotation" -Method DELETE -Path "/api/annotations/annotations/$annotationId" -ExpectedStatusCodes @(200, 204)
}

if ($collectionId -and $resourceId) {
    Test-Endpoint -Name "Remove Resource from Collection" -Method DELETE -Path "/api/collections/$collectionId/resources/$resourceId" -ExpectedStatusCodes @(200, 204)
}

if ($collectionId) {
    Test-Endpoint -Name "Delete Collection" -Method DELETE -Path "/api/collections/$collectionId" -ExpectedStatusCodes @(200, 204)
}

if ($resourceId) {
    Test-Endpoint -Name "Delete Resource" -Method DELETE -Path "/api/resources/$resourceId" -ExpectedStatusCodes @(200, 204)
}

# ============================================================
# SUMMARY
# ============================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "TEST SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Total Tests: $script:totalTests" -ForegroundColor White
Write-Host "Passed: $script:passedTests" -ForegroundColor Green
Write-Host "Failed: $script:failedTests" -ForegroundColor Red
Write-Host "Success Rate: $([Math]::Round(($script:passedTests / $script:totalTests) * 100, 2))%" -ForegroundColor White
Write-Host ""

# Show failed tests
if ($script:failedTests -gt 0) {
    Write-Host "Failed Tests:" -ForegroundColor Red
    $script:testResults | Where-Object { $_.Status -eq "FAIL" } | ForEach-Object {
        Write-Host "   ❌ $($_.Test) - $($_.Method) $($_.Path)" -ForegroundColor Red
        if ($_.Error) {
            Write-Host "      Error: $($_.Error)" -ForegroundColor Gray
        }
    }
    Write-Host ""
}

# Export results
$resultsFile = "endpoint_test_results_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
$script:testResults | ConvertTo-Json -Depth 10 | Out-File $resultsFile
Write-Host "Results exported to: $resultsFile" -ForegroundColor Gray
Write-Host ""

# Final status
if ($script:failedTests -eq 0) {
    Write-Host "🎉 ALL TESTS PASSED!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "⚠️  SOME TESTS FAILED" -ForegroundColor Yellow
    exit 1
}
