# Signaling server

FastAPI WebSocket relay that pairs a host session with one viewer and forwards
SDP/ICE messages between them. See `../docs/api-spec.md` for the message
contract.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Test

```bash
pytest -v
```

## Docker

```bash
docker build -t screentracker-signaling .
docker run -p 8000:8000 screentracker-signaling
```
