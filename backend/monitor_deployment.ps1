Write-Host "Monitoring Render deployment..." -ForegroundColor Cyan

$maxAttempts = 60
$attempt = 0

while ($attempt -lt $maxAttempts) {
    $attempt++
    
    try {
        $response = Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/health" -Method GET -TimeoutSec 5 -ErrorAction Stop
        
        if ($response.status -eq "healthy") {
            Write-Host "Deployment successful!" -ForegroundColor Green
            break
        }
    } catch {
        Write-Host "[$attempt/$maxAttempts] Waiting..." -ForegroundColor Gray
    }
    
    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host "Testing resource creation..." -ForegroundColor Cyan

$headers = @{
    "Content-Type" = "application/json"
    "Origin" = "https://pharos-cloud-api.onrender.com"
}

$body = @{
    url = "https://example.com"
    title = "Test Resource"
    description = "Testing CLOUD mode fix"
} | ConvertTo-Json

try {
    $result = Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/resources" -Method POST -Body $body -Headers $headers -ErrorAction Stop
    
    Write-Host "Success!" -ForegroundColor Green
    Write-Host "Resource ID: $($result.id)" -ForegroundColor Cyan
    Write-Host "Status: $($result.status)" -ForegroundColor Cyan
    
} catch {
    Write-Host "Failed!" -ForegroundColor Red
    Write-Host $_.Exception.Message
}
