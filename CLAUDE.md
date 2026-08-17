# ScreenTracker

Open-source, self-hosted screen viewing between your own devices over the internet (any OS host → any browser viewer), built with WebRTC.

See `HANDOFF.md` for current work-in-progress state.

## Architecture (why)
- **Host app is native (Python), not browser-based** — needs to run headless/as a background service without depending on a browser tab staying open, and Phase 2 (input injection) needs OS-level access anyway. See `docs/superpowers/specs/2026-08-17-remote-screen-view-design.md` for the full reasoning and rejected alternatives.
- **WebRTC via `aiortc`/browser-native API, not reinvented** — encode, adaptive bitrate and NAT traversal are solved problems; only the signaling protocol (small, app-specific) is hand-rolled.
- Monolith-first does not apply here — the system is inherently distributed (host, signaling server, TURN server, viewer are separate processes on separate machines by necessity, not by choice).

## Running locally
See Quick start in `README.md`.

## Environment variables
See `.env.example`. `SIGNALING_SERVER_URL` (host app) and `VITE_SIGNALING_SERVER_URL` (viewer app) must point at the same signaling server.

## Constraints
- $0/month cost — Azure for Students free tier only, no paid tier resources
- Session codes are unguessable (`secrets.token_urlsafe`) and expire after 5 minutes if unclaimed
- Phase 1 scope only: screen viewing, no input control (Phase 2, separate spec)

## Docs
- `docs/architecture.md` — component/sequence diagrams, decisions log
- `docs/api-spec.md` — WebSocket message contract
- `docs/superpowers/specs/` — dated design specs
- `docs/superpowers/plans/` — dated implementation plans
