# Ingest a Go repository to test Phase 2 polyglot AST support

$API_BASE = "https://pharos-cloud-api.onrender.com"
$ADMIN_TOKEN = $env:PHAROS_ADMIN_TOKEN

if (-not $ADMIN_TOKEN) {
    Write-Host "ERROR: PHAROS_ADMIN_TOKEN environment variable not set"
    exit 1
}

$REPO = "github.com/fatih/color"

Write-Host ("=" * 80)
Write-Host "INGESTING GO REPOSITORY: $REPO"
Write-Host ("=" * 80)

$headers = @{
    "Authorization" = "Bearer $ADMIN_TOKEN"
}

Write-Host ""
Write-Host "Starting ingestion..."
Write-Host "This may take 2-5 minutes depending on repo size..."
Write-Host ""

try {
    $response = Invoke-RestMethod -Uri "$API_BASE/api/v1/ingestion/ingest/$REPO" `
        -Method Post `
        -Headers $headers `
        -TimeoutSec 600
    
    Write-Host "SUCCESS: Ingestion completed"
    Write-Host ""
    Write-Host "Results:"
    Write-Host "  Repository: $($response.repository)"
    Write-Host "  Status: $($response.status)"
    Write-Host "  Message: $($response.message)"
    
    if ($response.stats) {
        Write-Host ""
        Write-Host "Statistics:"
        Write-Host "  Files processed: $($response.stats.files_processed)"
        Write-Host "  Chunks created: $($response.stats.chunks_created)"
        Write-Host "  Resources created: $($response.stats.resources_created)"
    }
    
    Write-Host ""
    Write-Host ("=" * 80)
    Write-Host "NEXT: Search for Go code to verify AST extraction"
    Write-Host ("=" * 80)
    
} catch {
    Write-Host "ERROR: Ingestion failed"
    Write-Host "Status: $($_.Exception.Response.StatusCode.value__)"
    Write-Host "Message: $_"
    
    if ($_.ErrorDetails.Message) {
        Write-Host "Details: $($_.ErrorDetails.Message)"
    }
    
    exit 1
}
