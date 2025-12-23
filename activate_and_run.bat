@echo off
echo Activating CDI API Environment and Starting Server...
echo.

REM Activate conda environment
call conda activate cdi_api
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to activate cdi_api environment
    echo Please run setup_and_run.bat first to create the environment
    pause
    exit /b 1
)

echo Environment activated!
echo.
echo Starting FastAPI server...
echo Server will be available at: http://0.0.0.0:8001
echo API Documentation: http://0.0.0.0:8001/docs
echo.
echo Press Ctrl+C to stop the server
echo.

python api.py

pause

