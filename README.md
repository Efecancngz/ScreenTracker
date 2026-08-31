# ScreenTracker

Open-source screen viewing between your own devices, over the internet, from any OS host to any browser viewer.

## Why
Watching your PC's screen live from your phone (or any other device) when you're away from it, without relying on closed-source tools like TeamViewer — and as a hands-on WebRTC/networking learning project.

## Stack
Python (FastAPI, aiortc, mss) · React (Vite, TypeScript) · WebRTC · coturn · Azure App Service

## Prerequisites
Install these two first if you don't have them — **on the "Add to PATH"
step of each installer, check the box.** Skipping that is the #1 cause of
"command not found" errors below.
- [Python 3.11+](https://www.python.org/downloads/) (tested on 3.12) —
  on the first install screen, check **"Add python.exe to PATH"**
- [Node.js 18+ LTS](https://nodejs.org/) — the installer adds it to PATH
  automatically

Windows is required to use `start.bat`/`start-dev.bat`. The signaling
server and host app also run standalone on macOS/Linux (host app falls
back from `dxcam` to `mss` for screen capture off Windows).

## Quick start (Windows, daily use — recommended for most people)
```bash
git clone https://github.com/Efecancngz/ScreenTracker.git
cd ScreenTracker
cp .env.example .env
```
Then double-click **`start.bat`**. That's it — first run automatically
installs everything it needs (signaling server deps, host app deps, the
launcher's own tiny dependency set, and the viewer build) and puts a tray
icon in the taskbar corner with:
- the current session code (and a "Copy code" action),
- **New session** — drops the current viewer and issues a fresh code,
- **Open logs folder**,
- **Quit** — stops everything.

The viewer itself is served by the signaling server as a static build (no
separate dev server needed), so a phone only needs one URL:
`http://<signaling-server-host>:<port>/`.

The one-time install step can take a minute or two the first time
(downloading Python packages); every run after that starts instantly.

## Development: visible consoles + hot reload

Use **`start-dev.bat`** instead while working on the code — it opens the
signaling server, host app, and viewer **dev server** (`npm run dev`, hot
reload) each in their own visible console window. It doesn't auto-install
dependencies the way `start.bat` does, so install them by hand first:
```bash
cd signaling-server && pip install -r requirements.txt && cd ..
cd host-app && pip install -r requirements.txt && cd ..
cd viewer-app && npm install && cd ..
```
Or run the pieces one at a time by hand:

```bash
# Signaling server
cd signaling-server && python -m uvicorn app.main:app --reload

# Host app (separate terminal)
cd host-app && python -m screentracker_host.main

# Viewer app (separate terminal)
cd viewer-app && npm run dev
```

## Troubleshooting

- **"Python was not found on PATH" / "Node.js was not found on PATH"**
  (`start.bat`) — install from the links in [Prerequisites](#prerequisites);
  for Python specifically, check "Add python.exe to PATH" on the first
  installer screen, then close and reopen the folder/terminal before
  double-clicking `start.bat` again.
- **`start.bat` seems stuck on "Installing... dependencies" for a while** —
  normal on first run only, it's downloading Python packages (aiortc in
  particular can take a minute). Subsequent runs skip this and start
  instantly.
- **"'uvicorn' is not recognized as an internal or external command"**
  (only relevant to the manual/`start-dev.bat` commands below, `start.bat`
  doesn't hit this) — run `python -m uvicorn app.main:app --reload` instead
  of bare `uvicorn`.
- **Used a venv and now `start.bat`/`start-dev.bat` can't find
  Python/uvicorn/pip packages** — activate the venv in the same terminal
  before running the `.bat` file, or don't use a venv at all and let the
  scripts use your system Python (what they assume by default).
- **Phone on the same WiFi can't reach the signaling server URL** — add a
  Windows Firewall inbound allow rule for the port in your `.env`
  (`SIGNALING_SERVER_PORT`, default 8000): Windows Defender Firewall with
  Advanced Security → Inbound Rules → New Rule → Port → TCP → that port.
- **Phone on a different network (mobile data, another WiFi) can't connect
  at all** — LAN-only setups don't reach across networks; see
  [Deployment](docs/deployment.md) for Tailscale, the tested way to reach
  your PC from anywhere.
- **Host app hangs instead of failing when connecting to the signaling
  server** — use `127.0.0.1` in `.env`'s `SIGNALING_SERVER_URL`, not
  `localhost`. On Windows `localhost` resolves to IPv6 `::1` first, which
  uvicorn's `0.0.0.0` binding never answers.
- **Blank/black screen on the phone over plain HTTP + LAN IP** — expected
  for very old browsers only; current builds already work around the
  `crypto.randomUUID()` secure-context restriction. If you still see it,
  make sure `viewer-app/dist` was rebuilt after pulling (`npm run build`).

## Documentation
- [Deployment](docs/deployment.md)
- [Architecture](docs/architecture.md)
- [API spec](docs/api-spec.md)
- [Design spec — Phase 1](docs/superpowers/specs/2026-08-17-remote-screen-view-design.md)

## License
MIT — see [LICENSE](LICENSE)
