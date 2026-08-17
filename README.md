# ScreenTracker

Open-source screen viewing between your own devices, over the internet, from any OS host to any browser viewer.

## Why
Watching your PC's screen live from your phone (or any other device) when you're away from it, without relying on closed-source tools like TeamViewer — and as a hands-on WebRTC/networking learning project.

## Stack
Python (FastAPI, aiortc, mss) · React (Vite, TypeScript) · WebRTC · coturn · Azure App Service

## Quick start
```bash
git clone <repo-url>
cp .env.example .env

# Signaling server
cd signaling-server && pip install -r requirements.txt && uvicorn app.main:app --reload

# Host app (separate terminal)
cd host-app && pip install -r requirements.txt && python -m screentracker_host.main

# Viewer app (separate terminal)
cd viewer-app && npm install && npm run dev
```

## Documentation
- [Architecture](docs/architecture.md)
- [API spec](docs/api-spec.md)
- [Design spec — Phase 1](docs/superpowers/specs/2026-08-17-remote-screen-view-design.md)

## License
MIT — see [LICENSE](LICENSE)
