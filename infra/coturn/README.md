# TURN server (coturn)

Relays media when a direct peer-to-peer connection between host and viewer
can't be established (common when either side is behind restrictive NAT).
Needs a persistent UDP port, so it's deployed to a small Azure VM or
Container Instance — not App Service.

## Deploy (Azure Container Instance, matches the $0/month constraint)

1. Replace `CHANGE_ME_STRONG_PASSWORD` in `turnserver.conf` with a generated
   secret; put the same value in `.env` as `TURN_PASSWORD`.
2. Create the container group in an Azure-for-Students-allowed region:

```bash
az container create \
  --resource-group rg-screentracker \
  --name screentracker-turn \
  --image coturn/coturn:latest \
  --ports 3478 5349 \
  --protocol UDP \
  --command-line "turnserver -c /etc/coturn/turnserver.conf" \
  --azure-file-volume-share-name coturn-config \
  --azure-file-volume-mount-path /etc/coturn
```

3. Copy `turnserver.conf` into the mounted file share before starting the
   container (Azure Portal → Storage account → File share → Upload).

## Verify

Use the WebRTC sample Trickle ICE tester
(`https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/`)
with a `turn:` URI pointing at the container's public IP, port 3478, and the
credentials from step 1. A successful `relay` candidate confirms the TURN
server is reachable and authenticating correctly.
