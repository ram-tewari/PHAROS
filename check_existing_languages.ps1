# Check what languages are already indexed to test Phase 2

$API_BASE = "https://pharos-cloud-api.onrender.com"
$ADMIN_TOKEN = $env:PHAROS_ADMIN_TOKEN

if (-not $ADMIN_TOKEN) {
    Write-Host "ERROR: PHAROS_ADMIN_TOKEN not set"
    exit 1
}

$headers = @{
    "Authorization" = "Bearer $ADMIN_TOKEN"
    "Content-Type" = "application/json"
}

Write-Host ("=" * 80)
Write-Host "CHECKING EXISTING INDEXED LANGUAGES"
Write-Host ("=" * 80)
Write-Host ""

# Search for different languages
$languages = @("go", "rust", "typescript", "javascript", "java")

foreach ($lang in $languages) {
    Write-Host "Searching for $lang code..."
    
    $body = @{
        query = $lang
        strategy = "parent-child"
        top_k = 3
        include_code = $false
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "$API_BASE/api/search/advanced" `
            -Method Post `
            -Headers $headers `
            -Body $body `
            -ContentType "application/json"
        
        if ($response.total -gt 0) {
            Write-Host "  Found $($response.total) results"
            
            foreach ($result in $response.results) {
                $chunk = $result.chunk
                Write-Host "    - $($chunk.file_name) (ast_node_type: $($chunk.ast_node_type), symbol: $($chunk.symbol_name))"
            }
        } else {
            Write-Host "  No results found"
        }
    } catch {
        Write-Host "  Error: $_"
    }
    
    Write-Host ""
}

Write-Host ("=" * 80)
Write-Host "If any non-Python results show ast_node_type='function' or 'class',"
Write-Host "then Phase 2 polyglot AST is working!"
Write-Host ("=" * 80)
