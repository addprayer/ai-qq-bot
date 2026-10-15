@echo off
REM ===========================================================================
REM  AI QQ Bot - daily launcher
REM
REM  Double-click this file to start the bot.
REM  NapCat must already be running (see start_napcat.bat).
REM
REM  Extra: run "start_bot.bat --check" to only run the health checks.
REM ===========================================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "CHECK_ONLY=0"
if /i "%~1"=="--check" set "CHECK_ONLY=1"

echo ============================================================
echo   AI QQ Bot
echo ============================================================
echo.

REM --- 1. virtual environment -------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo.
    echo Please run these commands once:
    echo     python -m venv .venv
    echo     .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    if "%CHECK_ONLY%"=="0" pause
    exit /b 1
)
echo [OK] Virtual environment found.

REM --- 2. .env ----------------------------------------------------------------
if not exist ".env" (
    echo [ERROR] .env not found.
    echo.
    echo Please run:  copy .env.example .env
    echo then fill in AI_API_KEY and ONEBOT_ACCESS_TOKEN.
    echo.
    if "%CHECK_ONLY%"=="0" pause
    exit /b 1
)
echo [OK] .env found.

REM --- 3. config sanity check (keys, formats) ---------------------------------
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if __import__('config').get_settings().is_ai_configured else 2)"
if errorlevel 1 (
    echo [ERROR] AI_API_KEY is not configured properly.
    echo         Open .env in Notepad and fill in your real DeepSeek key.
    echo.
    if "%CHECK_ONLY%"=="0" pause
    exit /b 1
)
echo [OK] AI_API_KEY configured.

REM --- 4. NapCat --------------------------------------------------------------
powershell -NoProfile -Command "if (Test-NetConnection -ComputerName 127.0.0.1 -Port 6099 -InformationLevel Quiet -WarningAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo [WARN] NapCat is not running on port 6099.
    echo        Start it first with start_napcat.bat / start_all.bat.
    echo        The bot will still start, but QQ will not be connected.
) else (
    echo [OK] NapCat is running.
)

echo.
if "%CHECK_ONLY%"=="1" (
    echo Health check finished.
    if "%CHECK_ONLY%"=="0" pause
    exit /b 0
)

echo Starting the bot ...
echo.
echo ------------------------------------------------------------
echo   Success looks like:  Bot ^<your QQ number^> connected
echo   Keep this window open. Press Ctrl+C to stop.
echo ------------------------------------------------------------
echo.

".venv\Scripts\python.exe" bot.py

echo.
echo ============================================================
echo   The bot has stopped.
echo ============================================================
pause
