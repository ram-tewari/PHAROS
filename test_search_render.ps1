# Test Phase 1 search fixes on Render production API

$API_BASE = "https://pharos-cloud-api.onrender.com"
$ADMIN_TOKEN = $env:PHAROS_ADMIN_TOKEN

if (-not $ADMIN_TOKEN) {
    Write-Host "❌ PHAROS_ADMIN_TOKEN environment variable not set"
    Write-Host "Set it with: `$env:PHAROS_ADMIN_TOKEN='your-token'"
    exit 1
}

Write-Host "=" * 80
Write-Host "TESTING PHASE 1 SEARCH FIXES ON RENDER"
Write-Host "API: $API_BASE"
Write-Host "=" * 80

# Test 1: Health check
Write-Host ""
Write-Host "[Test 1] Health check..."
try {
    $response = Invoke-RestMethod -Uri "$API_BASE/health" -Method Get
    Write-Host "✅ Status: $($response.status)"
} catch {
    Write-Host "❌ Health check failed: $_"
    exit 1
}

# Test 2: Advanced search with include_code=true
Write-Host ""
Write-Host "[Test 2] Advanced search with include_code=true..."
$headers = @{
    "Authorization" = "Bearer $ADMIN_TOKEN"
    "Content-Type" = "application/json"
}

$body = @{
    query = "authentication"
    strategy = "parent-child"
    top_k = 3
    context_window = 2
    include_code = $true
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$API_BASE/api/search/advanced" `
        -Method Post `
        -Headers $headers `
        -Body $body `
        -ContentType "application/json"
    
    Write-Host "✅ Status: 200"
    Write-Host "✅ Latency: $([math]::Round($response.latency_ms, 1))ms"
    Write-Host "✅ Results: $($response.total)"
    
    # Check code_metrics
    if ($response.code_metrics) {
        Write-Host ""
    Write-Host "Code Fetch Metrics:"
        Write-Host "   Total chunks: $($response.code_metrics.total_chunks)"
        Write-Host "   Fetched: $($response.code_metrics.fetched)"
        Write-Host "   Cache hits: $($response.code_metrics.cache_hits)"
        Write-Host "   Errors: $($response.code_metrics.errors)"
        Write-Host "   Fetch time: $([math]::Round($response.code_metrics.fetch_time_ms, 1))ms"
    }
    
    # Validate first result
    if ($response.results.Count -gt 0) {
        Write-Host ""
        Write-Host "Validating first result..."
        $result = $response.results[0]
        $chunk = $result.chunk
        
        $checks = @{
            "id" = $chunk.id
            "file_name" = $chunk.file_name
            "github_uri" = $chunk.github_uri
            "start_line" = $chunk.start_line
            "end_line" = $chunk.end_line
            "symbol_name" = $chunk.symbol_name
            "ast_node_type" = $chunk.ast_node_type
            "code" = $chunk.code
            "source" = $chunk.source
        }
        
        $all_ok = $true
        foreach ($field in $checks.Keys) {
            $value = $checks[$field]
            if ($null -eq $value -or ($value -is [string] -and $value -eq "")) {
                Write-Host "   ❌ $field : MISSING"
                $all_ok = $false
            } else {
                $preview = $value.ToString().Substring(0, [Math]::Min(60, $value.ToString().Length))
                if ($value.ToString().Length -gt 60) {
                    $preview += "..."
                }
                Write-Host "   ✅ $field : $preview"
            }
        }
        
        # Check surrounding chunks
        $surrounding = $result.surrounding_chunks
        Write-Host ""
        Write-Host "Surrounding chunks: $($surrounding.Count)"
        if ($surrounding.Count -gt 0) {
            for ($i = 0; $i -lt [Math]::Min(2, $surrounding.Count); $i++) {
                $sc = $surrounding[$i]
                $code_present = if ($sc.code) { "✅" } else { "❌" }
                $status = if ($sc.code) { "present" } else { "MISSING" }
                Write-Host "   $code_present Chunk $($i+1): code=$status"
            }
        }
        
        if ($all_ok) {
            Write-Host ""
            Write-Host ("=" * 80)
            Write-Host "PHASE 1 VERIFICATION PASSED"
            Write-Host "All critical fields are populated correctly!"
            Write-Host ("=" * 80)
        } else {
            Write-Host ""
            Write-Host ("=" * 80)
            Write-Host "PHASE 1 VERIFICATION FAILED"
            Write-Host "Some fields are missing or empty"
            Write-Host ("=" * 80)
            exit 1
        }
    } else {
        Write-Host ""
        Write-Host "No results returned (database may be empty)"
    }
    
} catch {
    Write-Host "❌ Search failed: $_"
    Write-Host "Response: $($_.Exception.Response)"
    exit 1
}

Write-Host ""
Write-Host "All tests passed!"
Write-Host ""
Write-Host "Next: Re-ingest a non-Python repo to test Phase 2 polyglot AST"
