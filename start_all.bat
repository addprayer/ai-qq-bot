@echo off
REM ===========================================================================
REM  Start NapCat (the QQ side) with administrator rights, then start the bot.
REM
REM  Edit NAPCAT_DIR below if you installed NapCat somewhere else.
REM ===========================================================================
setlocal
chcp 65001 >nul

set "NAPCAT_DIR=C:\napcat\NapCat.52230.Shell"

echo ============================================================
echo   AI QQ Bot - full startup (NapCat + Bot)
echo ============================================================
echo.
echo   NapCat directory: %NAPCAT_DIR%
echo.

if not exist "%NAPCAT_DIR%\napcat.bat" (
    echo [ERROR] napcat.bat not found in that directory.
    echo.
    echo Please open this file in Notepad and edit the NAPCAT_DIR line
    echo so it points to your own NapCat folder.
    echo.
    pause
    exit /b 1
)

REM --- If NapCat is already listening on the WebUI port, skip starting it ----
powershell -NoProfile -Command "if (Test-NetConnection -ComputerName 127.0.0.1 -Port 6099 -InformationLevel Quiet -WarningAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [OK] NapCat is already running - skipping.
    goto :run_bot
)

echo Starting NapCat in a new administrator window ...
echo   A UAC prompt will appear. Click "Yes" to allow it.
echo.
start "NapCat" cmd /c "cd /d ^"%NAPCAT_DIR%^" && napcat.bat"

echo Waiting for NapCat to be ready (up to 90 seconds) ...
for /l %%i in (1,1,45) do (
    powershell -NoProfile -Command "if (Test-NetConnection -ComputerName 127.0.0.1 -Port 6099 -InformationLevel Quiet -WarningAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
    if not errorlevel 1 goto :napcat_ready
    timeout /t 2 /nobreak >nul
)

echo.
echo [WARN] NapCat did not open port 6099 in time.
echo        Check the "NapCat" window: you may need to scan the QR code to log in.
echo        Continuing anyway - the bot will reconnect automatically once NapCat is up.
echo.
goto :run_bot

:napcat_ready
echo [OK] NapCat is running.
echo.

:run_bot
echo Loading the daily launcher ...
echo.
call "%~dp0start_bot.bat"
