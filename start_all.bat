@echo off
REM ===========================================================================
REM  AI QQ Bot - full startup (NapCat + Bot)
REM
REM  This is the file you double-click every day.
REM  Edit NAPCAT_DIR below if you installed NapCat somewhere else.
REM ===========================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set "NAPCAT_DIR=C:\napcat\NapCat.52230.Shell"
REM 用「快速登录」脚本启动：带 QQ 号复用本地会话，避免每次都扫码。
REM 若哪天想手动扫码登录，把它临时改回 napcat.bat 即可。
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

echo Starting NapCat in a new administrator window ...
echo   A UAC prompt may appear. Click "Yes" to allow it.
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
    echo        Check the "NapCat" window: you may need to scan the QR code to log in.
    echo        Continuing anyway - the bot reconnects automatically once NapCat is up.
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
