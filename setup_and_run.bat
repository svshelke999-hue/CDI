@echo off
echo ========================================
echo CDI FastAPI Setup and Run Script
echo ========================================
echo.

REM Check if conda is available
where conda >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Conda is not found in PATH
    echo Please install Anaconda or Miniconda first
    pause
    exit /b 1
)

echo Step 1: Creating conda environment...
call conda create -n cdi_api python=3.10 -y
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Environment might already exist, continuing...
)

echo.
echo Step 2: Activating environment...
call conda activate cdi_api
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to activate environment
    pause
    exit /b 1
)

echo.
echo Step 3: Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Step 4: Installing dependencies from requirements.txt...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Starting FastAPI server...
echo Server will be available at: http://0.0.0.0:8001
echo API Documentation: http://0.0.0.0:8001/docs
echo.
echo Press Ctrl+C to stop the server
echo.

python api.py

pause

