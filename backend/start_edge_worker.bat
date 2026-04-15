@echo off
REM Pharos Edge Worker Startup Script (Windows)
REM This script starts the edge worker with proper environment configuration

echo ========================================
echo Pharos Edge Worker - Startup
echo ========================================
echo.

REM Check if .env.edge exists
if not exist .env.edge (
    echo ERROR: .env.edge file not found!
    echo Please copy .env.edge.example to .env.edge and configure it.
    pause
    exit /b 1
)

REM Load environment from .env.edge
echo Loading environment from .env.edge...
for /f "usebackq tokens=1,* delims==" %%a in (".env.edge") do (
    set "line=%%a"
    REM Skip comments and empty lines
    if not "!line:~0,1!"=="#" if not "%%a"=="" (
        set "%%a=%%b"
    )
)

REM Verify MODE is set to EDGE
if not "%MODE%"=="EDGE" (
    echo ERROR: MODE must be set to EDGE in .env.edge
    echo Current MODE: %MODE%
    pause
    exit /b 1
)

echo ✓ Environment loaded
echo.

REM Check if virtual environment is activated
python -c "import sys; sys.exit(0 if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) else 1)" 2>nul
if errorlevel 1 (
    echo WARNING: Virtual environment not activated
    echo Activate with: .venv\Scripts\activate
    echo.
)

REM Check if PyTorch is installed
echo Checking PyTorch installation...
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA Available:', torch.cuda.is_available())" 2>nul
if errorlevel 1 (
    echo ERROR: PyTorch not installed!
    echo Install with: pip install -r requirements-edge.txt
    pause
    exit /b 1
)
echo.

REM Check if sentence-transformers is installed
echo Checking sentence-transformers installation...
python -c "import sentence_transformers; print('sentence-transformers:', sentence_transformers.__version__)" 2>nul
if errorlevel 1 (
    echo ERROR: sentence-transformers not installed!
    echo Install with: pip install -r requirements-edge.txt
    pause
    exit /b 1
)
echo.

REM Start edge worker
echo ========================================
echo Starting Edge Worker...
echo ========================================
echo.
echo Press Ctrl+C to stop
echo.

python -m app.edge_worker

REM Capture exit code
set EXIT_CODE=%ERRORLEVEL%

echo.
echo ========================================
echo Edge Worker Stopped (Exit Code: %EXIT_CODE%)
echo ========================================
pause
