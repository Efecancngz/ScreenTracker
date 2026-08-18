# Deployment

## Tailscale (recommended — tested)

The simplest way to reach your PC from anywhere: install [Tailscale](https://tailscale.com)
on both your PC and your phone (or any other viewer device). Tailscale gives every
device on your account a stable private IP, reachable from anywhere, without opening
router ports or deploying anything to the cloud.

1. Create a free Tailscale account and install it on your PC and phone.
2. On your PC, find your Tailscale IP: `tailscale ip -4` (or check the Tailscale
   system tray icon).
3. Run the signaling server bound to all interfaces so Tailscale can reach it:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
4. Set `SIGNALING_SERVER_URL` and `VITE_SIGNALING_SERVER_URL` in `.env` to your
   Tailscale IP, e.g. `ws://100.x.y.z:8000/ws`.
5. Run the host app and the viewer app as usual (see the root `README.md`).
6. On your phone, open the viewer app's address using your PC's Tailscale IP
   (e.g. `http://100.x.y.z:5173`) — this works over any network your phone is on,
   not just the same WiFi.

**Why no TURN server is needed here:** Tailscale handles NAT traversal itself at
the network layer. The public Google STUN server ScreenTracker already uses as a
baseline is enough of a fallback for the rare case it's needed.

**Windows Firewall:** if the signaling/viewer ports don't respond from your phone,
add an inbound allow rule (see the root `README.md` troubleshooting notes).

**Verified cross-network (2026-08-18):** confirmed end-to-end with the PC on
its home WiFi and the phone on mobile data (different networks, no shared
LAN) — session join, device pairing approval, and live screen streaming all
worked over the Tailscale IP.

## Azure App Service + coturn (alternative — not tested)

The original design targeted Azure App Service for the signaling server and an
Azure Container Instance running `coturn` for TURN relay — see
`infra/coturn/README.md` and `docs/superpowers/specs/2026-08-17-remote-screen-view-design.md`
for the intended shape of this deployment. **This path has not been exercised
end-to-end.** If you try it and hit a problem, please open an issue — or fork the
repo and adapt it to your environment; contributions documenting a working Azure
setup are welcome.

## Tunnel services — ngrok / Cloudflare Tunnel (alternative — not tested)

A lighter-weight alternative to a full cloud deployment: run the signaling server
locally and expose it with a tunneling tool like `ngrok http 8000` or a Cloudflare
Tunnel. **This path has not been exercised end-to-end** — TURN's UDP relay in
particular may not work cleanly through some tunnel providers. If you try it and
hit a problem, please open an issue or fork and adapt.
