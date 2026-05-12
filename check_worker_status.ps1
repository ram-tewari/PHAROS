# Check Pharos Edge Worker Status
# This script queries the production API to check worker health

Write-Host "=== Pharos Edge Worker Status ===" -ForegroundColor Cyan
Write-Host ""

try {
    $response = Invoke-WebRequest -Uri "https://pharos-cloud-api.onrender.com/api/v1/ingestion/health/worker" -Method GET
    $data = $response.Content | ConvertFrom-Json
    
    Write-Host "Worker State: " -NoNewline
    switch ($data.state) {
        "online" {
            Write-Host $data.state -ForegroundColor Green
        }
        "degraded" {
            Write-Host $data.state -ForegroundColor Yellow
        }
        "offline" {
            Write-Host $data.state -ForegroundColor Red
        }
        default {
            Write-Host $data.state -ForegroundColor Gray
        }
    }
    
    Write-Host ""
    
    if ($data.last_seen_unix) {
        $lastSeen = [DateTimeOffset]::FromUnixTimeSeconds([long]$data.last_seen_unix).LocalDateTime
        Write-Host "Last Heartbeat: $lastSeen" -ForegroundColor Gray
        Write-Host "Seconds Ago: $([math]::Round($data.seconds_since_last_seen, 1))s" -ForegroundColor Gray
        Write-Host "Threshold: $($data.threshold_seconds)s" -ForegroundColor Gray
    } else {
        Write-Host "Last Heartbeat: Never" -ForegroundColor Red
    }
    
    Write-Host ""
    
    if ($data.worker_meta) {
        Write-Host "Worker Details:" -ForegroundColor Cyan
        Write-Host "  Worker ID: $($data.worker_meta.worker_id)" -ForegroundColor Gray
        Write-Host "  Version: $($data.worker_meta.version)" -ForegroundColor Gray
        Write-Host "  Model: $($data.worker_meta.embedding_model)" -ForegroundColor Gray
        Write-Host "  DLQ Drained: $($data.worker_meta.queue_drained_count)" -ForegroundColor Gray
    }
    
    Write-Host ""
    
    # Provide actionable advice
    if ($data.state -eq "online") {
        Write-Host "✓ Worker is healthy and ready to process tasks" -ForegroundColor Green
    } elseif ($data.state -eq "degraded") {
        Write-Host "⚠ Worker heartbeat is stale (>5 minutes old)" -ForegroundColor Yellow
        Write-Host "  Action: Restart the worker with: .\restart_worker.ps1" -ForegroundColor Yellow
    } else {
        Write-Host "✗ Worker is offline (no heartbeat recorded)" -ForegroundColor Red
        Write-Host "  Action: Start the worker with: .\restart_worker.ps1" -ForegroundColor Red
    }
    
} catch {
    Write-Host "ERROR: Failed to check worker status" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
