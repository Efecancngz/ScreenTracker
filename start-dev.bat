@echo off
REM Development launcher: starts the signaling server, host app, and viewer
REM dev server, each in its own VISIBLE window with logs on screen and the
REM viewer hot-reloading on code changes. Use this while working on the
REM code. For daily use, use start.bat instead (one hidden background app,
REM system tray icon, no consoles).
setlocal enabledelayedexpansion

cd /d "%~dp0"

if not exist ".env" (
    echo No .env file found next to start.bat.
    echo Copy .env.example to .env and fill in SIGNALING_SERVER_URL first.
    pause
    exit /b 1
)

REM Load .env into this process's environment. Blank lines and lines
REM starting with # (comments, including commented-out TURN settings) are
REM skipped.
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "key=%%A"
    if not "!key:~0,1!"=="#" if not "!key!"=="" (
        set "%%A=%%B"
    )
)

if "%SIGNALING_SERVER_URL%"=="" (
    echo SIGNALING_SERVER_URL is not set in .env — the host app needs it.
    pause
    exit /b 1
)

echo Starting ScreenTracker...
echo   Signaling server: %SIGNALING_SERVER_HOST%:%SIGNALING_SERVER_PORT%
echo   Host app connects to: %SIGNALING_SERVER_URL%
echo.

start "ScreenTracker - Signaling Server" cmd /k "cd /d "%~dp0signaling-server" && python -m uvicorn app.main:app --host %SIGNALING_SERVER_HOST% --port %SIGNALING_SERVER_PORT%"

REM Give the signaling server a moment to come up before the host app tries
REM to connect to it.
timeout /t 2 /nobreak >nul

start "ScreenTracker - Host App" cmd /k "cd /d "%~dp0host-app" && python -m screentracker_host.main"

start "ScreenTracker - Viewer" cmd /k "cd /d "%~dp0viewer-app" && npm run dev"

echo All three services are starting in separate windows.
echo Closing this window will NOT stop them — close each one individually when you're done.
