# Simple Pharos CLI Test Script
$env:PHAROS_API_URL = "http://127.0.0.1:8000"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PHAROS CLI ENDPOINT TEST" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$commands = @(
    @{Name="Version"; Cmd="python -m pharos_cli version"},
    @{Name="Info"; Cmd="python -m pharos_cli info"},
    @{Name="System Help"; Cmd="python -m pharos_cli system --help"},
    @{Name="Resource Help"; Cmd="python -m pharos_cli resource --help"},
    @{Name="Collection Help"; Cmd="python -m pharos_cli collection --help"},
    @{Name="Search Help"; Cmd="python -m pharos_cli search --help"},
    @{Name="Annotate Help"; Cmd="python -m pharos_cli annotate --help"},
    @{Name="Quality Help"; Cmd="python -m pharos_cli quality --help"},
    @{Name="Taxonomy Help"; Cmd="python -m pharos_cli taxonomy --help"},
    @{Name="Graph Help"; Cmd="python -m pharos_cli graph --help"},
    @{Name="Recommend Help"; Cmd="python -m pharos_cli recommend --help"},
    @{Name="Code Help"; Cmd="python -m pharos_cli code --help"},
    @{Name="Ask Help"; Cmd="python -m pharos_cli ask --help"},
    @{Name="Chat Help"; Cmd="python -m pharos_cli chat --help"},
    @{Name="Batch Help"; Cmd="python -m pharos_cli batch --help"},
    @{Name="Backup Help"; Cmd="python -m pharos_cli backup --help"},
    @{Name="Auth Help"; Cmd="python -m pharos_cli auth --help"},
    @{Name="Config Help"; Cmd="python -m pharos_cli config --help"}
)

$success = 0
$failed = 0

foreach ($test in $commands) {
    Write-Host "Testing: $($test.Name)..." -NoNewline
    
    try {
        cd pharos-cli
        $output = Invoke-Expression "$($test.Cmd) 2>&1" | Out-String
        cd ..
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host " SUCCESS" -ForegroundColor Green
            $success++
        } else {
            Write-Host " FAILED (Exit: $LASTEXITCODE)" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host " ERROR" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "RESULTS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Success: $success" -ForegroundColor Green
Write-Host "Failed:  $failed" -ForegroundColor Red
Write-Host "Total:   $($commands.Count)" -ForegroundColor White
