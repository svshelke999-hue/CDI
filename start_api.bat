@echo off
echo Starting CDI Compliance FastAPI Server...
echo.
echo Server will be available at:
echo   - Local: http://localhost:8001
echo   - Network: http://10.50.20.175:8001
echo.
echo API Documentation: http://localhost:8001/docs
echo.
echo NOTE: Do NOT use http://0.0.0.0:8001 in browser!
echo       Use localhost or your machine IP instead.
echo.
python api.py

