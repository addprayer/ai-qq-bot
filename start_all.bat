@echo off
REM ===========================================================================
REM  AI QQ Bot - full startup (NapCat + Bot)
REM
REM  Double-click this file every day.
REM  Edit NAPCAT_DIR below if you installed NapCat somewhere else.
REM ===========================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

REM --- NapCat has to run as administrator (it injects into the QQ process), ---
REM --- so re-launch this script elevated when we are not administrator yet. ---
if /i "%~1"=="--elevated" goto :admin_ok
REM Check for a High Integrity token (SID S-1-16-12288). Locale independent,
REM and unlike fltmc / net session it does not depend on extra services.
whoami /groups 2>nul | find "S-1-16-12288" >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator privileges ...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '--elevated' -Verb RunAs"
    exit /b
)
:admin_ok
echo Administrator mode detected.
echo.

set "NAPCAT_DIR=C:\napcat\NapCat.52230.Shell"
REM Use the quick-login launcher: pass the QQ number so the saved local
REM session is reused and the QR code is normally not needed.
REM Change back to napcat.bat if you ever want to scan manually.
set "NAPCAT_BAT=napcat.quick.bat"
set "NAPCAT_PORT=6099"

echo ============================================================
echo   AI QQ Bot - full startup (NapCat + Bot)
echo ============================================================
echo.
echo   NapCat directory: %NAPCAT_DIR%
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo         Please run:  python -m venv .venv
    echo                      .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "%NAPCAT_DIR%\%NAPCAT_BAT%" (
    echo [ERROR] %NAPCAT_BAT% was not found in that directory.
    echo.
    echo Please open this file in Notepad and edit the NAPCAT_DIR line
    echo so that it points to your own NapCat folder.
    echo.
    pause
    exit /b 1
)

REM --- If NapCat is already listening on the WebUI port, skip starting it ----
call :port_open
if "!PORT_OPEN!"=="1" (
    echo [OK] NapCat is already running - skipping.
    goto :run_bot
)

echo Starting NapCat in a new window ...
echo.
REM NOTE: use "start /d <dir>" so that no quote-escaping is needed.
REM Escaping quotes around a path containing spaces breaks the command
REM (it produced: 'napcat.bat"' is not recognized as an internal or
REM  external command).
start "NapCat" /d "%NAPCAT_DIR%" cmd /c "%NAPCAT_BAT%"

echo Waiting for NapCat to be ready (up to 90 seconds) ...
".venv\Scripts\python.exe" "tools\wait_port.py" %NAPCAT_PORT% --wait 90 --quiet
if errorlevel 1 (
    echo.
    echo [WARN] NapCat did not open port %NAPCAT_PORT% in time.
    echo        Check the "NapCat" window: it may need a QR scan.
    echo        Continuing anyway - the bot reconnects automatically.
    echo.
) else (
    echo [OK] NapCat is running.
    echo.
)

:run_bot
echo Loading the daily launcher ...
echo.
call "%~dp0start_bot.bat"
exit /b %ERRORLEVEL%

REM ---------------------------------------------------------------------------
REM  Subroutine: set PORT_OPEN=1 when something listens on the NapCat port
REM ---------------------------------------------------------------------------
:port_open
set "PORT_OPEN=0"
".venv\Scripts\python.exe" "tools\wait_port.py" %NAPCAT_PORT% --quiet
if not errorlevel 1 set "PORT_OPEN=1"
goto :eof
