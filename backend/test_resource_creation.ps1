$headers = @{
    "Content-Type" = "application/json"
    "Origin" = "https://pharos-cloud-api.onrender.com"
}

$body = @{
    url = "https://example.com"
    title = "Test Resource"
    description = "Testing end-to-end resource creation"
} | ConvertTo-Json

Write-Host "Testing resource creation..." -ForegroundColor Cyan

try {
    $response = Invoke-RestMethod -Uri "https://pharos-cloud-api.onrender.com/api/resources" -Method POST -Body $body -Headers $headers -ErrorAction Stop
    
    Write-Host "Success!" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error!" -ForegroundColor Red
    Write-Host $_.Exception.Message
    if ($_.ErrorDetails) {
        Write-Host $_.ErrorDetails.Message
    }
}
