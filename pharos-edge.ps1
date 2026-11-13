# pharos-edge launcher
# Usage:
#   .\pharos-edge.ps1 start                # Windows-native worker
#   .\pharos-edge.ps1 start --wsl          # Worker under WSL
#   .\pharos-edge.ps1 status
#   .\pharos-edge.ps1 logs -n 100
#   .\pharos-edge.ps1 stop
#   .\pharos-edge.ps1 restart
#   .\pharos-edge.ps1 doctor

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $here "backend\pharos_edge.py"

if (-not (Test-Path $py)) {
    Write-Error "Could not find $py"
    exit 1
}

python $py @args
exit $LASTEXITCODE
