# ScreenTracker

Open-source screen viewing between your own devices, over the internet, from any OS host to any browser viewer.

## Why
Watching your PC's screen live from your phone (or any other device) when you're away from it, without relying on closed-source tools like TeamViewer — and as a hands-on WebRTC/networking learning project.

## Stack
Python (FastAPI, aiortc, mss) · React (Vite, TypeScript) · WebRTC · coturn · Azure App Service

## Quick start (one-time setup)
```bash
git clone <repo-url>
cp .env.example .env  # fill in SIGNALING_SERVER_URL etc.

cd signaling-server && pip install -r requirements.txt && cd ..
cd host-app && pip install -r requirements.txt && cd ..
cd viewer-app && npm install && npm run build && cd ..
```

## Windows: daily use — background app + tray icon

Double-click **`start.bat`** (repo root). It runs the signaling server and
host app hidden in the background, and puts a tray icon in the taskbar
corner with:
- the current session code (and a "Copy code" action),
- **New session** — drops the current viewer and issues a fresh code,
- **Open logs folder**,
- **Quit** — stops everything.

The viewer itself is served by the signaling server as a static build (no
separate dev server needed), so a phone only needs one URL:
`http://<signaling-server-host>:<port>/`.

First run installs the launcher's own small dependency set (`pystray`,
`Pillow`) automatically and builds the viewer if it hasn't been built yet.

## Development: visible consoles + hot reload

Use **`start-dev.bat`** instead while working on the code — it opens the
signaling server, host app, and viewer **dev server** (`npm run dev`, hot
reload) each in their own visible console window. Or run the pieces by hand:

```bash
# Signaling server
cd signaling-server && uvicorn app.main:app --reload

# Host app (separate terminal)
cd host-app && python -m screentracker_host.main

# Viewer app (separate terminal)
cd viewer-app && npm run dev
```

## Documentation
- [Deployment](docs/deployment.md)
- [Architecture](docs/architecture.md)
- [API spec](docs/api-spec.md)
- [Design spec — Phase 1](docs/superpowers/specs/2026-08-17-remote-screen-view-design.md)

## License
MIT — see [LICENSE](LICENSE)
