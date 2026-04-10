@echo off
REM Run complete performance test: populate + benchmark

echo ==========================================
echo PHASE 5: PERFORMANCE TESTING
echo ==========================================
echo.

REM Step 1: Populate database
echo Step 1: Populating database with test data...
python populate_test_data.py
if %ERRORLEVEL% NEQ 0 (
    echo Failed to populate database
    exit /b 1
)

echo.
echo Step 2: Running performance benchmarks...
python benchmark_context_assembly.py
if %ERRORLEVEL% NEQ 0 (
    echo Benchmarks failed
    exit /b 1
)

echo.
echo Performance testing complete!
echo Check benchmark_results.json for detailed results
