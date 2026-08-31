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
    echo Python was not found on PATH.
    echo Install it from https://www.python.org/downloads/ — on the first
    echo installer screen, check "Add python.exe to PATH" — then try again.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo Node.js was not found on PATH.
    echo Install it from https://nodejs.org/ ^(LTS version^) and try again.
    pause
    exit /b 1
)

python -c "import pystray, PIL" >nul 2>nul
if errorlevel 1 (
    echo Installing launcher dependencies ^(pystray, Pillow^)...
    python -m pip install -r "%~dp0launcher\requirements.txt"
)

python -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo Installing signaling server dependencies — first run only, this can take a minute...
    python -m pip install -r "%~dp0signaling-server\requirements.txt"
)

python -c "import aiortc, mss, pynput" >nul 2>nul
if errorlevel 1 (
    echo Installing host app dependencies — first run only, this can take a minute...
    python -m pip install -r "%~dp0host-app\requirements.txt"
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
