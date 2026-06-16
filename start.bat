@echo off
echo ========================================
echo   MobilityOS - Starting Server
echo ========================================

cd /d "%~dp0backend"

IF NOT EXIST ".env" (
    echo Creating .env from template...
    copy .env.example .env
    echo.
    echo IMPORTANT: Edit backend\.env and add your API keys:
    echo   - GOOGLE_MAPS_KEY
    echo   - OPENAI_KEY
    echo.
    pause
)

echo Installing dependencies...
pip install -r requirements.txt --break-system-packages -q

echo.
echo Starting MobilityOS on http://localhost:8000
echo Press Ctrl+C to stop
echo.
python main.py
pause
