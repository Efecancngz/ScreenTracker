@echo off
REM Daily-use launcher: starts the ScreenTracker background app (signaling
REM server + host app, both hidden, plus a system tray icon showing the
REM session code and letting you start a fresh session or quit). No console
REM windows. For a visible, hot-reloading development setup, use
REM start-dev.bat instead.
setlocal

cd /d "%~dp0"

if not exist ".env" (
    echo No .env file found next to start.bat.
    echo Copy .env.example to .env and fill in SIGNALING_SERVER_URL first.
    pause
    exit /b 1
)

where pythonw >nul 2>nul
if errorlevel 1 (
    echo pythonw was not found on PATH. Install Python from python.org
    echo ^(it ships alongside python.exe^) and try again.
    pause
    exit /b 1
)

python -c "import pystray, PIL" >nul 2>nul
if errorlevel 1 (
    echo Installing launcher dependencies ^(pystray, Pillow^)...
    python -m pip install -r "%~dp0launcher\requirements.txt"
)

if not exist "viewer-app\dist\index.html" (
    echo Viewer has not been built yet — building it now...
    pushd viewer-app
    call npm install
    call npm run build
    popd
)

start "" pythonw "%~dp0launcher\tray_app.py"
echo ScreenTracker is starting in the background — look for its icon in the system tray.
