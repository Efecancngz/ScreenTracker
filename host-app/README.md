# Host app

Native background process that captures the screen and streams it over WebRTC
to whichever viewer joins its session. Requires `SIGNALING_SERVER_URL` (see
`../.env.example`).

## Run locally

```bash
pip install -r requirements.txt
export SIGNALING_SERVER_URL=ws://localhost:8000/ws   # PowerShell: $env:SIGNALING_SERVER_URL="..."
python -m screentracker_host.main
```

## Test

```bash
pytest -v
```

Manual smoke test only for `main.py` itself — it wires together capture and
WebRTC, both already unit-tested in isolation; a full run requires a live
signaling server and a real viewer (see Task 15 in the implementation plan).
