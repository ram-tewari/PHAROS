# PowerShell script to restart backend with TEST_MODE enabled

Write-Host "Stopping any running backend processes..." -ForegroundColor Yellow

# Find and stop uvicorn processes
$processes = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*uvicorn*" -or $_.CommandLine -like "*app.main*"
}

if ($processes) {
    Write-Host "Found $($processes.Count) backend process(es), stopping..." -ForegroundColor Yellow
    $processes | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Host "Backend stopped." -ForegroundColor Green
} else {
    Write-Host "No backend processes found." -ForegroundColor Cyan
}

Write-Host "`nStarting backend with TEST_MODE enabled..." -ForegroundColor Yellow
Write-Host "TEST_MODE bypasses authentication for testing purposes.`n" -ForegroundColor Cyan

# Set environment variable and start backend
$env:TESTING = "true"

Set-Location backend

Write-Host "Starting uvicorn..." -ForegroundColor Green
Write-Host "Backend will be available at: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Swagger UI: http://127.0.0.1:8000/docs`n" -ForegroundColor Cyan

# Start uvicorn
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
