@echo off
echo ========================================
echo Restarting Backend with TEST_MODE
echo ========================================
echo.
echo TEST_MODE bypasses authentication for testing purposes.
echo.

echo Setting TESTING=true...
set TESTING=true

echo Changing to backend directory...
cd backend

echo.
echo Starting backend...
echo Backend will be available at: http://127.0.0.1:8000
echo Swagger UI: http://127.0.0.1:8000/docs
echo.
echo Press Ctrl+C to stop the backend
echo.

python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
