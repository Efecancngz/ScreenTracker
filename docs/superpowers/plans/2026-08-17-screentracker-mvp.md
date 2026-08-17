# ScreenTracker Faz 1 (MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the project owner watch their PC's screen live, from any of their own devices (phone or another PC), over the internet — even across different networks — via a self-hosted signaling + TURN relay.

**Architecture:** Four independently deployable pieces: a native Python host app (screen capture via `mss` + WebRTC via `aiortc`) that never depends on a browser tab; a FastAPI WebSocket signaling server that pairs a host session with one viewer and relays SDP/ICE messages; a `coturn` TURN server for NAT traversal when a direct peer connection can't be established; and a React/Vite viewer web app that joins a session and renders the incoming WebRTC video stream. Signaling server and TURN server are deployed to Azure (App Service + a separate VM/Container Instance, since TURN needs a persistent UDP port App Service doesn't offer).

**Tech Stack:** Python 3.12 (FastAPI, aiortc, mss, pytest), TypeScript/React (Vite, Vitest, Testing Library), coturn, Azure App Service.

**Spec:** `docs/superpowers/specs/2026-08-17-remote-screen-view-design.md`

## Global Constraints

- Cost: $0/month — Azure for Students free tier only, never a paid tier resource
- Host platforms: Windows, macOS, Linux. Viewer: any modern browser (Chrome, Edge, Firefox, Safari)
- Session codes must be unguessable (`secrets.token_urlsafe`, ≥16 bytes) and expire 5 minutes after creation if unclaimed
- Phase 1 scope only — no input control (mouse/keyboard), no multi-viewer/invite system, no audio, no persistent database (in-memory session store is sufficient)
- Code, identifiers, and commit messages: English. Commit format: Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`), imperative mood, no AI co-author trailer — ever
- Every backend change ships with a test
- Errors shown to the end user are human-readable; stack traces and raw provider errors stay in server logs only
- Branch naming: `feat/<short-description>`, one logical change per PR

---

## File Structure

```
ScreenTracker/
├── README.md, CLAUDE.md, HANDOFF.md, LICENSE, .gitignore, .env.example
├── docs/
│   ├── architecture.md
│   ├── api-spec.md
│   └── superpowers/{specs,plans}/
├── signaling-server/                  # FastAPI WebSocket relay
│   ├── requirements.txt
│   ├── app/{main.py, session_manager.py, models.py}
│   ├── tests/{test_session_manager.py, test_models.py, test_main.py}
│   └── Dockerfile
├── host-app/                          # Native Python capture + WebRTC peer
│   ├── requirements.txt
│   ├── screentracker_host/{capture.py, signaling_client.py, webrtc_peer.py, main.py}
│   └── tests/{test_capture.py, test_signaling_client.py, test_webrtc_peer.py}
├── viewer-app/                        # React/Vite viewer
│   ├── package.json, vite.config.ts, index.html
│   ├── src/{App.tsx, App.module.css, main.tsx}
│   ├── src/styles/{tokens.css, global.css}
│   ├── src/hooks/{useSignalingSocket.ts, useWebRTCViewer.ts}
│   ├── src/components/{SessionJoinForm.tsx, SessionJoinForm.module.css, VideoPlayer.tsx, VideoPlayer.module.css}
│   └── tests/{SessionJoinForm.test.tsx, useSignalingSocket.test.ts, VideoPlayer.test.tsx, App.test.tsx}
└── infra/coturn/{turnserver.conf, README.md}
```

Each of the three apps (signaling-server, host-app, viewer-app) is independently runnable and testable — this drives the task order below: signaling server first (everything else depends on its message contract), then host app, then viewer app, then infra, then a manual end-to-end pass.

---

### Task 1: Repo scaffolding

**Files:**
- Create: `README.md`, `CLAUDE.md`, `HANDOFF.md`, `LICENSE`, `.gitignore`, `.env.example`
- Create: `docs/architecture.md`, `docs/api-spec.md`

**Interfaces:** None — this task produces no code, only project scaffolding later tasks and the human reference.

- [ ] **Step 1: Create `.gitignore`**

```
# Python
__pycache__/
*.pyc
.venv/
venv/

# Node
node_modules/
dist/

# Env
.env

# IDE
.vscode/
.idea/
```

- [ ] **Step 2: Create `.env.example`**

```
# Signaling server
SIGNALING_SERVER_HOST=0.0.0.0
SIGNALING_SERVER_PORT=8000

# Host app
SIGNALING_SERVER_URL=ws://localhost:8000/ws

# Viewer app (Vite requires the VITE_ prefix to expose a var to the browser)
VITE_SIGNALING_SERVER_URL=ws://localhost:8000/ws

# TURN server credentials
TURN_SERVER_URL=turn:your-turn-server:3478
TURN_USERNAME=screentracker
TURN_PASSWORD=changeme
```

- [ ] **Step 3: Create `LICENSE`** (MIT, copyright Efecan Cengiz, 2026)

```
MIT License

Copyright (c) 2026 Efecan Cengiz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Create `README.md`**

```md
# ScreenTracker

Open-source screen viewing between your own devices, over the internet, from any OS host to any browser viewer.

## Why
Watching your PC's screen live from your phone (or any other device) when you're away from it, without relying on closed-source tools like TeamViewer — and as a hands-on WebRTC/networking learning project.

## Stack
Python (FastAPI, aiortc, mss) · React (Vite, TypeScript) · WebRTC · coturn · Azure App Service

## Quick start
\`\`\`bash
git clone <repo-url>
cp .env.example .env

# Signaling server
cd signaling-server && pip install -r requirements.txt && uvicorn app.main:app --reload

# Host app (separate terminal)
cd host-app && pip install -r requirements.txt && python -m screentracker_host.main

# Viewer app (separate terminal)
cd viewer-app && npm install && npm run dev
\`\`\`

## Documentation
- [Architecture](docs/architecture.md)
- [API spec](docs/api-spec.md)
- [Design spec — Phase 1](docs/superpowers/specs/2026-08-17-remote-screen-view-design.md)

## License
MIT — see [LICENSE](LICENSE)
```

- [ ] **Step 5: Create `CLAUDE.md`**

```md
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
```

- [ ] **Step 6: Create `HANDOFF.md`**

```md
# Handoff — ScreenTracker
Son güncelleme: 2026-08-17 00:00, güncelleyen: Claude Sonnet 5

## Şu an ne yapılıyor
Faz 1 (MVP) implementasyon planı çıkarıldı, repo iskeleti kuruluyor.

## Sıradaki somut adım
Task 2'ye geç: signaling server'ın session manager ve mesaj modellerini yaz.

## Bilinmesi gerekenler
- Azure for Students hesabı doğrulandı, kaynak oluşturma çalışıyor
- TURN sunucusu (coturn) kalıcı UDP port istediği için Azure App Service'e değil, ayrı bir VM/Container Instance'a kurulacak

## İlgili dosyalar
- docs/superpowers/specs/2026-08-17-remote-screen-view-design.md — Faz 1 tasarımı
- docs/superpowers/plans/2026-08-17-screentracker-mvp.md — bu plan

## Son 3 commit
- (henüz yok)
```

- [ ] **Step 7: Create `docs/architecture.md`**

```md
# Architecture

## Components

\`\`\`mermaid
graph LR
    Host["Host App<br/>(Python: aiortc + mss)"]
    Signal["Signaling Server<br/>(FastAPI + WebSocket)"]
    Turn["TURN Server<br/>(coturn)"]
    Viewer["Viewer Web App<br/>(React + WebRTC)"]

    Host -- "WebSocket: session mgmt,<br/>SDP/ICE exchange" --> Signal
    Viewer -- "WebSocket: session mgmt,<br/>SDP/ICE exchange" --> Signal
    Host -. "media stream<br/>(P2P veya relay)" .-> Turn
    Turn -. "media stream" .-> Viewer
    Host == "media stream (doğrudan P2P mümkünse)" ==> Viewer
\`\`\`

## Session flow

\`\`\`mermaid
sequenceDiagram
    participant H as Host App
    participant S as Signaling Server
    participant V as Viewer

    H->>S: create-session
    S-->>H: session_id (link/kod)
    V->>S: join-session(session_id)
    S-->>H: peer-joined
    H->>S: offer (SDP)
    S-->>V: offer (SDP)
    V->>S: answer (SDP)
    S-->>H: answer (SDP)
    H->>S: ice-candidate
    S-->>V: ice-candidate
    V->>S: ice-candidate
    S-->>H: ice-candidate
    Note over H,V: ICE tamamlanınca medya doğrudan veya TURN üzerinden akar
    H-->>V: video stream (WebRTC media)
\`\`\`

## Decisions log

- **Native host app, not browser-based**: keeping the host process persistent (no browser tab dependency) and ready for Phase 2 OS-level input injection outweighed the simplicity of a pure browser-to-browser WebRTC app. See design spec for the rejected alternatives (pure-browser, Electron, from-scratch transport).
- **`aiortc` + `mss` over a from-scratch capture/encode pipeline**: WebRTC transport is a solved problem; only the signaling protocol is hand-rolled.
- **In-memory session store, no database**: Phase 1 has no requirement that survives a signaling server restart.
```

- [ ] **Step 8: Create `docs/api-spec.md`**

```md
# Signaling WebSocket API

Single endpoint: `ws://<signaling-host>/ws`. All messages are JSON objects with a
`type` field.

| Message | Direction | Payload |
|---|---|---|
| `create-session` | Host → Server | — |
| `session-created` | Server → Host | `session_id: string` |
| `join-session` | Viewer → Server | `session_id: string` |
| `peer-joined` | Server → Host | — |
| `offer` | Host → Server → Viewer | `sdp: string` |
| `answer` | Viewer → Server → Host | `sdp: string` |
| `ice-candidate` | either direction, relayed | `candidate: string`, `sdp_mid?: string`, `sdp_mline_index?: number` |
| `session-expired` | Server → Viewer | `reason: "not-found" \| "expired"` |
| `peer-disconnected` | Server → remaining peer | — |
```

- [ ] **Step 9: Commit**

```bash
cd C:/dev/ScreenTracker
git add README.md CLAUDE.md HANDOFF.md LICENSE .gitignore .env.example docs/architecture.md docs/api-spec.md
git commit -m "docs: scaffold project (README, CLAUDE.md, HANDOFF.md, architecture, API spec)"
```

---

### Task 2: Signaling server — session manager and message models

**Files:**
- Create: `signaling-server/requirements.txt`
- Create: `signaling-server/app/__init__.py` (empty)
- Create: `signaling-server/app/session_manager.py`
- Create: `signaling-server/app/models.py`
- Test: `signaling-server/tests/test_session_manager.py`
- Test: `signaling-server/tests/test_models.py`

**Interfaces:**
- Produces: `SessionManager.create_session(host_connection_id: str) -> Session`, `SessionManager.join_session(session_id: str, viewer_connection_id: str) -> Session`, `SessionManager.get_session(session_id: str) -> Session | None`, `SessionManager.remove_session(session_id: str) -> None`, exceptions `SessionNotFoundError`, `SessionExpiredError`. `Session` dataclass with `session_id: str`, `host_connection_id: str`, `viewer_connection_id: str | None`.
- Produces: `parse_inbound_message(raw: dict) -> InboundMessage` and Pydantic models `CreateSessionMessage`, `JoinSessionMessage`, `SdpMessage`, `IceCandidateMessage`.

- [ ] **Step 1: Create `signaling-server/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
pydantic==2.9.2
websockets==13.1
httpx==0.27.2
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Write the failing tests for the session manager**

`signaling-server/tests/test_session_manager.py`:

```python
import time

import pytest

from app.session_manager import SessionExpiredError, SessionManager, SessionNotFoundError


def test_create_session_returns_unique_id():
    manager = SessionManager()
    session_a = manager.create_session(host_connection_id="host-1")
    session_b = manager.create_session(host_connection_id="host-2")
    assert session_a.session_id != session_b.session_id


def test_join_session_attaches_viewer():
    manager = SessionManager()
    session = manager.create_session(host_connection_id="host-1")
    joined = manager.join_session(session.session_id, viewer_connection_id="viewer-1")
    assert joined.viewer_connection_id == "viewer-1"


def test_join_unknown_session_raises():
    manager = SessionManager()
    with pytest.raises(SessionNotFoundError):
        manager.join_session("does-not-exist", viewer_connection_id="viewer-1")


def test_join_expired_session_raises_and_removes_it():
    manager = SessionManager(ttl_seconds=0.01)
    session = manager.create_session(host_connection_id="host-1")
    time.sleep(0.02)
    with pytest.raises(SessionExpiredError):
        manager.join_session(session.session_id, viewer_connection_id="viewer-1")
    assert manager.get_session(session.session_id) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run (from `signaling-server/`): `pytest tests/test_session_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.session_manager'`

- [ ] **Step 4: Implement `signaling-server/app/session_manager.py`**

```python
import secrets
import time
from dataclasses import dataclass, field

SESSION_TTL_SECONDS = 300.0  # 5 minutes to be claimed by a viewer

# 6 characters from a 32-symbol alphabet is ~30 bits of entropy — combined
# with the 5-minute TTL, guessing a live code is impractical. The alphabet
# drops 0/O/1/I/L so a code read aloud or hand-typed on a phone can't be
# misread (matches the viewer's segmented 6-box code input).
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6


@dataclass
class Session:
    session_id: str
    host_connection_id: str
    viewer_connection_id: str | None = None
    created_at: float = field(default_factory=time.monotonic)


class SessionNotFoundError(Exception):
    pass


class SessionExpiredError(Exception):
    pass


class SessionManager:
    def __init__(self, ttl_seconds: float = SESSION_TTL_SECONDS) -> None:
        self._sessions: dict[str, Session] = {}
        self._ttl_seconds = ttl_seconds

    def create_session(self, host_connection_id: str) -> Session:
        session_id = self._generate_unique_code()
        session = Session(session_id=session_id, host_connection_id=host_connection_id)
        self._sessions[session_id] = session
        return session

    def _generate_unique_code(self) -> str:
        while True:
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
            if code not in self._sessions:
                return code

    def join_session(self, session_id: str, viewer_connection_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        if session.viewer_connection_id is None and self._is_expired(session):
            del self._sessions[session_id]
            raise SessionExpiredError(session_id)
        session.viewer_connection_id = viewer_connection_id
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _is_expired(self, session: Session) -> bool:
        return (time.monotonic() - session.created_at) > self._ttl_seconds
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_session_manager.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Write the failing tests for message models**

`signaling-server/tests/test_models.py`:

```python
import pytest

from app.models import JoinSessionMessage, SdpMessage, parse_inbound_message


def test_parse_join_session_message():
    parsed = parse_inbound_message({"type": "join-session", "session_id": "abc123"})
    assert isinstance(parsed, JoinSessionMessage)
    assert parsed.session_id == "abc123"


def test_parse_offer_message():
    parsed = parse_inbound_message({"type": "offer", "sdp": "v=0..."})
    assert isinstance(parsed, SdpMessage)
    assert parsed.type == "offer"


def test_parse_unknown_type_raises():
    with pytest.raises(ValueError):
        parse_inbound_message({"type": "not-a-real-type"})
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 8: Implement `signaling-server/app/models.py`**

```python
from typing import Literal, Union

from pydantic import BaseModel


class CreateSessionMessage(BaseModel):
    type: Literal["create-session"] = "create-session"


class SessionCreatedMessage(BaseModel):
    type: Literal["session-created"] = "session-created"
    session_id: str


class JoinSessionMessage(BaseModel):
    type: Literal["join-session"] = "join-session"
    session_id: str


class PeerJoinedMessage(BaseModel):
    type: Literal["peer-joined"] = "peer-joined"


class SdpMessage(BaseModel):
    type: Literal["offer", "answer"]
    sdp: str


class IceCandidateMessage(BaseModel):
    type: Literal["ice-candidate"] = "ice-candidate"
    candidate: str
    sdp_mid: str | None = None
    sdp_mline_index: int | None = None


class SessionExpiredMessage(BaseModel):
    type: Literal["session-expired"] = "session-expired"
    reason: str


class PeerDisconnectedMessage(BaseModel):
    type: Literal["peer-disconnected"] = "peer-disconnected"


InboundMessage = Union[CreateSessionMessage, JoinSessionMessage, SdpMessage, IceCandidateMessage]

OutboundMessage = Union[
    SessionCreatedMessage,
    PeerJoinedMessage,
    SdpMessage,
    IceCandidateMessage,
    SessionExpiredMessage,
    PeerDisconnectedMessage,
]

_INBOUND_MODELS: dict[str, type[BaseModel]] = {
    "create-session": CreateSessionMessage,
    "join-session": JoinSessionMessage,
    "offer": SdpMessage,
    "answer": SdpMessage,
    "ice-candidate": IceCandidateMessage,
}


def parse_inbound_message(raw: dict) -> InboundMessage:
    model = _INBOUND_MODELS.get(raw.get("type"))
    if model is None:
        raise ValueError(f"Unknown message type: {raw.get('type')!r}")
    return model.model_validate(raw)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 10: Commit**

```bash
cd C:/dev/ScreenTracker/signaling-server
git add requirements.txt app/__init__.py app/session_manager.py app/models.py tests/test_session_manager.py tests/test_models.py
git commit -m "feat: add signaling server session manager and message models"
```

---

### Task 3: Signaling server — WebSocket endpoint

**Files:**
- Create: `signaling-server/app/main.py`
- Test: `signaling-server/tests/test_main.py`

**Interfaces:**
- Consumes: `SessionManager` and its methods/exceptions from Task 2; `parse_inbound_message` and message models from Task 2.
- Produces: `app` (FastAPI instance) at `signaling-server/app/main.py`, exposing `/ws` — consumed by Task 4's Dockerfile and Task 6's `SignalingClient` (via a live server, not an import).

- [ ] **Step 1: Write the failing tests**

`signaling-server/tests/test_main.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_full_session_handshake_relays_offer_and_answer():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect("/ws") as viewer_ws:
        host_ws.send_json({"type": "create-session"})
        created = host_ws.receive_json()
        assert created["type"] == "session-created"
        session_id = created["session_id"]

        viewer_ws.send_json({"type": "join-session", "session_id": session_id})
        peer_joined = host_ws.receive_json()
        assert peer_joined["type"] == "peer-joined"

        host_ws.send_json({"type": "offer", "sdp": "v=0..."})
        relayed_offer = viewer_ws.receive_json()
        assert relayed_offer == {"type": "offer", "sdp": "v=0..."}

        viewer_ws.send_json({"type": "answer", "sdp": "v=0..."})
        relayed_answer = host_ws.receive_json()
        assert relayed_answer == {"type": "answer", "sdp": "v=0..."}


def test_join_nonexistent_session_returns_session_expired():
    client = TestClient(app)
    with client.websocket_connect("/ws") as viewer_ws:
        viewer_ws.send_json({"type": "join-session", "session_id": "does-not-exist"})
        response = viewer_ws.receive_json()
        assert response == {"type": "session-expired", "reason": "not-found"}


def test_host_disconnect_notifies_viewer():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        with client.websocket_connect("/ws") as viewer_ws:
            viewer_ws.send_json({"type": "join-session", "session_id": session_id})
            host_ws.receive_json()  # peer-joined, not under test here

            host_ws.close()
            disconnect_notice = viewer_ws.receive_json()
            assert disconnect_notice == {"type": "peer-disconnected"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `signaling-server/`): `pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Implement `signaling-server/app/main.py`**

```python
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.models import parse_inbound_message
from app.session_manager import SessionExpiredError, SessionManager, SessionNotFoundError

app = FastAPI()
session_manager = SessionManager()

# connection_id -> WebSocket, so relayed messages reach the right peer
_connections: dict[str, WebSocket] = {}
# connection_id -> session_id, so a disconnect can find the peer to notify
_connection_sessions: dict[str, str] = {}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    connection_id = str(uuid.uuid4())
    _connections[connection_id] = websocket

    try:
        while True:
            raw = await websocket.receive_json()
            try:
                message = parse_inbound_message(raw)
            except ValueError:
                continue

            if message.type == "create-session":
                session = session_manager.create_session(connection_id)
                _connection_sessions[connection_id] = session.session_id
                await websocket.send_json(
                    {"type": "session-created", "session_id": session.session_id}
                )
            elif message.type == "join-session":
                await _handle_join(connection_id, message.session_id, websocket)
            elif message.type in ("offer", "answer", "ice-candidate"):
                await _relay_to_peer(connection_id, raw)
    except WebSocketDisconnect:
        await _handle_disconnect(connection_id)


async def _handle_join(connection_id: str, session_id: str, websocket: WebSocket) -> None:
    try:
        session = session_manager.join_session(session_id, connection_id)
    except SessionNotFoundError:
        await websocket.send_json({"type": "session-expired", "reason": "not-found"})
        return
    except SessionExpiredError:
        await websocket.send_json({"type": "session-expired", "reason": "expired"})
        return

    _connection_sessions[connection_id] = session_id
    host_ws = _connections.get(session.host_connection_id)
    if host_ws is not None:
        await host_ws.send_json({"type": "peer-joined"})


async def _relay_to_peer(connection_id: str, raw: dict) -> None:
    peer_ws = _peer_websocket_for(connection_id)
    if peer_ws is not None:
        await peer_ws.send_json(raw)


async def _handle_disconnect(connection_id: str) -> None:
    peer_ws = _peer_websocket_for(connection_id)
    session_id = _connection_sessions.pop(connection_id, None)
    _connections.pop(connection_id, None)

    if peer_ws is not None:
        await peer_ws.send_json({"type": "peer-disconnected"})
    if session_id is not None:
        session_manager.remove_session(session_id)


def _peer_websocket_for(connection_id: str) -> WebSocket | None:
    session_id = _connection_sessions.get(connection_id)
    if session_id is None:
        return None
    session = session_manager.get_session(session_id)
    if session is None:
        return None
    peer_id = (
        session.viewer_connection_id
        if connection_id == session.host_connection_id
        else session.host_connection_id
    )
    return _connections.get(peer_id) if peer_id else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd C:/dev/ScreenTracker/signaling-server
git add app/main.py tests/test_main.py
git commit -m "feat: add signaling server WebSocket endpoint"
```

---

### Task 4: Signaling server — packaging and local run docs

**Files:**
- Create: `signaling-server/Dockerfile`
- Create: `signaling-server/README.md`

**Interfaces:**
- Consumes: `app.main:app` from Task 3.
- Produces: a runnable container image entry point, consumed only by deployment (manual step in Task 14/15), not by other tasks' code.

- [ ] **Step 1: Create `signaling-server/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `signaling-server/README.md`**

```md
# Signaling server

FastAPI WebSocket relay that pairs a host session with one viewer and forwards
SDP/ICE messages between them. See `../docs/api-spec.md` for the message
contract.

## Run locally

\`\`\`bash
pip install -r requirements.txt
uvicorn app.main:app --reload
\`\`\`

## Test

\`\`\`bash
pytest -v
\`\`\`

## Docker

\`\`\`bash
docker build -t screentracker-signaling .
docker run -p 8000:8000 screentracker-signaling
\`\`\`
```

- [ ] **Step 3: Verify the container builds**

Run: `docker build -t screentracker-signaling ./signaling-server`
Expected: build succeeds with no errors

- [ ] **Step 4: Commit**

```bash
cd C:/dev/ScreenTracker
git add signaling-server/Dockerfile signaling-server/README.md
git commit -m "chore: add signaling server Dockerfile and README"
```

---

### Task 5: Host app — screen capture module

**Files:**
- Create: `host-app/requirements.txt`
- Create: `host-app/screentracker_host/__init__.py` (empty)
- Create: `host-app/screentracker_host/capture.py`
- Test: `host-app/tests/test_capture.py`

**Interfaces:**
- Produces: `Frame` dataclass (`width: int`, `height: int`, `data: np.ndarray` shape `(height, width, 4)`, BGRA), `capture_frame(monitor_index: int = 1) -> Frame` — consumed by Task 7's `ScreenCaptureTrack`.

- [ ] **Step 1: Create `host-app/requirements.txt`**

```
aiortc==1.10.0
mss==9.0.2
numpy==2.1.2
websockets==13.1
av==13.1.0
pytest==8.3.3
pytest-asyncio==0.24.0
```

(`aiortc==1.10.0` requires `av<14.0.0,>=9.0.0`, which `av==13.1.0` satisfies —
`aiortc==1.9.0` requires `av<13.0.0` and would make this file uninstallable.
Verified against PyPI package metadata.)

- [ ] **Step 2: Write the failing test**

`host-app/tests/test_capture.py`:

```python
from unittest.mock import MagicMock, patch

import numpy as np

from screentracker_host.capture import capture_frame


def test_capture_frame_returns_frame_with_expected_shape():
    fake_raw = MagicMock()
    fake_raw.width = 100
    fake_raw.height = 50

    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        mock_sct.monitors = [None, {"left": 0, "top": 0, "width": 100, "height": 50}]
        mock_sct.grab.return_value = fake_raw
        mock_mss_cls.return_value.__enter__.return_value = mock_sct

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((50, 100, 4), dtype=np.uint8),
        ):
            frame = capture_frame()

    assert frame.width == 100
    assert frame.height == 50
    assert frame.data.shape == (50, 100, 4)
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `host-app/`): `pytest tests/test_capture.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'screentracker_host.capture'`

- [ ] **Step 4: Implement `host-app/screentracker_host/capture.py`**

```python
from dataclasses import dataclass

import mss
import numpy as np


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    data: np.ndarray  # BGRA, shape (height, width, 4)


def capture_frame(monitor_index: int = 1) -> Frame:
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        raw = sct.grab(monitor)
        data = np.array(raw)
        return Frame(width=raw.width, height=raw.height, data=data)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_capture.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd C:/dev/ScreenTracker/host-app
git add requirements.txt screentracker_host/__init__.py screentracker_host/capture.py tests/test_capture.py
git commit -m "feat: add host app screen capture module"
```

---

### Task 6: Host app — signaling client

**Files:**
- Create: `host-app/screentracker_host/signaling_client.py`
- Test: `host-app/tests/test_signaling_client.py`

**Interfaces:**
- Consumes: none from earlier tasks.
- Produces: `SignalingClient(url: str)` with `async connect()`, `async close()`, `async send(message: dict)`, `async receive() -> dict`, `async create_session() -> str`, `async messages() -> AsyncIterator[dict]` — consumed by Task 8's CLI entrypoint.

- [ ] **Step 1: Write the failing test**

`host-app/tests/test_signaling_client.py`:

```python
import json

import pytest
import websockets

from screentracker_host.signaling_client import SignalingClient


async def _session_created_handler(websocket):
    raw = await websocket.recv()
    message = json.loads(raw)
    assert message["type"] == "create-session"
    await websocket.send(json.dumps({"type": "session-created", "session_id": "test-session-id"}))
    await websocket.wait_closed()


@pytest.mark.asyncio
async def test_create_session_returns_session_id():
    async with websockets.serve(_session_created_handler, "localhost", 8765):
        client = SignalingClient("ws://localhost:8765")
        await client.connect()
        session_id = await client.create_session()
        await client.close()

    assert session_id == "test-session-id"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `host-app/`): `pytest tests/test_signaling_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'screentracker_host.signaling_client'`

- [ ] **Step 3: Implement `host-app/screentracker_host/signaling_client.py`**

```python
import json
from collections.abc import AsyncIterator
from typing import Any

import websockets


class SignalingClient:
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: websockets.WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        self._connection = await websockets.connect(self._url)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def send(self, message: dict[str, Any]) -> None:
        assert self._connection is not None, "call connect() first"
        await self._connection.send(json.dumps(message))

    async def receive(self) -> dict[str, Any]:
        assert self._connection is not None, "call connect() first"
        raw = await self._connection.recv()
        return json.loads(raw)

    async def create_session(self) -> str:
        await self.send({"type": "create-session"})
        response = await self.receive()
        if response["type"] != "session-created":
            raise RuntimeError(f"Unexpected response: {response}")
        return response["session_id"]

    async def messages(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            yield await self.receive()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_signaling_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/dev/ScreenTracker/host-app
git add screentracker_host/signaling_client.py tests/test_signaling_client.py
git commit -m "feat: add host app signaling client"
```

---

### Task 7: Host app — WebRTC peer

**Files:**
- Create: `host-app/screentracker_host/webrtc_peer.py`
- Test: `host-app/tests/test_webrtc_peer.py`

**Interfaces:**
- Consumes: `capture_frame` and `Frame` from `screentracker_host.capture` (Task 5).
- Produces: `ScreenCaptureTrack` (aiortc `VideoStreamTrack` subclass), `HostPeerConnection` with `async create_offer() -> RTCSessionDescription`, `async set_remote_answer(sdp: str) -> None`, `async add_ice_candidate(candidate) -> None`, `async close() -> None` — consumed by Task 8's CLI entrypoint.

- [ ] **Step 1: Write the failing test**

`host-app/tests/test_webrtc_peer.py`:

```python
import numpy as np
import pytest

from screentracker_host.capture import Frame
from screentracker_host.webrtc_peer import ScreenCaptureTrack


@pytest.mark.asyncio
async def test_recv_returns_video_frame_matching_capture_size(monkeypatch):
    fake_frame = Frame(width=4, height=2, data=np.zeros((2, 4, 4), dtype=np.uint8))
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.capture_frame", lambda monitor_index: fake_frame
    )

    track = ScreenCaptureTrack()
    video_frame = await track.recv()

    assert video_frame.width == 4
    assert video_frame.height == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `host-app/`): `pytest tests/test_webrtc_peer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'screentracker_host.webrtc_peer'`

- [ ] **Step 3: Implement `host-app/screentracker_host/webrtc_peer.py`**

```python
from __future__ import annotations

import fractions

import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

from screentracker_host.capture import capture_frame

VIDEO_TIME_BASE = fractions.Fraction(1, 90000)
TARGET_FPS = 15
_PTS_STEP = int(VIDEO_TIME_BASE.denominator / TARGET_FPS)


class ScreenCaptureTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self, monitor_index: int = 1) -> None:
        super().__init__()
        self._monitor_index = monitor_index
        self._pts = 0

    async def recv(self) -> VideoFrame:
        frame = capture_frame(self._monitor_index)
        rgb = frame.data[:, :, :3][:, :, ::-1]  # BGRA -> RGB
        video_frame = VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
        video_frame.pts = self._pts
        video_frame.time_base = VIDEO_TIME_BASE
        self._pts += _PTS_STEP
        return video_frame


class HostPeerConnection:
    def __init__(self) -> None:
        self._pc = RTCPeerConnection()
        self._pc.addTrack(ScreenCaptureTrack())

    async def create_offer(self) -> RTCSessionDescription:
        offer = await self._pc.createOffer()
        await self._pc.setLocalDescription(offer)
        return self._pc.localDescription

    async def set_remote_answer(self, sdp: str) -> None:
        await self._pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="answer"))

    async def add_ice_candidate(self, candidate) -> None:
        await self._pc.addIceCandidate(candidate)

    async def close(self) -> None:
        await self._pc.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_webrtc_peer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/dev/ScreenTracker/host-app
git add screentracker_host/webrtc_peer.py tests/test_webrtc_peer.py
git commit -m "feat: add host app WebRTC peer connection"
```

---

### Task 8: Host app — CLI entrypoint

**Files:**
- Create: `host-app/screentracker_host/main.py`
- Create: `host-app/README.md`

**Interfaces:**
- Consumes: `SignalingClient` (Task 6), `HostPeerConnection` (Task 7).
- Produces: `main()` CLI entrypoint. No later task consumes this programmatically — it's the runtime entry point, verified manually (screen capture + a live WebRTC connection can't be meaningfully unit-tested).

- [ ] **Step 1: Implement `host-app/screentracker_host/main.py`**

```python
import asyncio
import os

from screentracker_host.signaling_client import SignalingClient
from screentracker_host.webrtc_peer import HostPeerConnection


async def run() -> None:
    signaling_url = os.environ["SIGNALING_SERVER_URL"]
    client = SignalingClient(signaling_url)
    await client.connect()

    session_id = await client.create_session()
    print(f"Session ready. Share this code with your viewer: {session_id}")

    peer_connection = HostPeerConnection()

    async for message in client.messages():
        if message["type"] == "peer-joined":
            offer = await peer_connection.create_offer()
            await client.send({"type": "offer", "sdp": offer.sdp})
        elif message["type"] == "answer":
            await peer_connection.set_remote_answer(message["sdp"])
        elif message["type"] == "ice-candidate":
            await peer_connection.add_ice_candidate(message["candidate"])
        elif message["type"] == "peer-disconnected":
            print("Viewer disconnected.")
            break

    await peer_connection.close()
    await client.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create `host-app/README.md`**

```md
# Host app

Native background process that captures the screen and streams it over WebRTC
to whichever viewer joins its session. Requires `SIGNALING_SERVER_URL` (see
`../.env.example`).

## Run locally

\`\`\`bash
pip install -r requirements.txt
export SIGNALING_SERVER_URL=ws://localhost:8000/ws   # PowerShell: $env:SIGNALING_SERVER_URL="..."
python -m screentracker_host.main
\`\`\`

## Test

\`\`\`bash
pytest -v
\`\`\`

Manual smoke test only for `main.py` itself — it wires together capture and
WebRTC, both already unit-tested in isolation; a full run requires a live
signaling server and a real viewer (see Task 15 in the implementation plan).
```

- [ ] **Step 3: Manual smoke test**

Run: with the signaling server from Task 3 running locally (`uvicorn app.main:app --reload` in `signaling-server/`), run `python -m screentracker_host.main` in `host-app/`.
Expected: prints `Session ready. Share this code with your viewer: <code>` and does not crash while waiting for a peer. Stop with Ctrl+C.

- [ ] **Step 4: Commit**

```bash
cd C:/dev/ScreenTracker/host-app
git add screentracker_host/main.py README.md
git commit -m "feat: add host app CLI entrypoint"
```

---

### Task 9: Viewer app — scaffold and design tokens

**Files:**
- Create: `viewer-app/` (via `npm create vite@latest`), `viewer-app/package.json`, `viewer-app/vitest.config.ts`
- Create: `viewer-app/src/styles/tokens.css`
- Create: `viewer-app/src/styles/global.css`
- Modify: `viewer-app/index.html` (font loading)
- Modify: `viewer-app/src/main.tsx` (import global styles)

**Interfaces:**
- Produces: CSS custom properties (`--bg`, `--surface`, `--border`, `--text-primary`, `--text-secondary`, `--accent`, `--accent-contrast`, `--font-display`, `--font-body`, `--radius`, `--space-1`…`--space-5`, `--transition-fast`) — consumed by every styled component in Tasks 10–13.

Design direction (approved): dark-first with a light variant following system
preference, warm near-black/near-white neutrals (not pure black/white or cool
gray), a single copper/amber accent (not neon, not gradient) evoking an
instrument-panel indicator light. Display/data text in IBM Plex Mono, body
text in IBM Plex Sans. No gradients, no glassmorphism, light motion only
(CSS transitions, no animation library) and `prefers-reduced-motion` is
respected globally.

- [ ] **Step 1: Scaffold the Vite project**

Run (from `C:/dev/ScreenTracker/`):

```bash
npm create vite@latest viewer-app -- --template react-ts
cd viewer-app
npm install
npm install -D vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom
```

- [ ] **Step 2: Create `viewer-app/src/styles/tokens.css`**

```css
:root {
  /* light (default) */
  --font-display: "IBM Plex Mono", ui-monospace, monospace;
  --font-body: "IBM Plex Sans", system-ui, sans-serif;

  --bg: #f7f5f1;
  --surface: #ffffff;
  --border: #e3e0d9;
  --text-primary: #17181b;
  --text-secondary: #6b6a65;
  --accent: #a85f26;
  --accent-contrast: #ffffff;

  --radius: 4px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 16px;
  --space-4: 24px;
  --space-5: 40px;

  --transition-fast: 120ms ease;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0c0d0f;
    --surface: #17181b;
    --border: #2a2c30;
    --text-primary: #ecead4;
    --text-secondary: #8c8b86;
    --accent: #c77d3b;
    --accent-contrast: #0c0d0f;
  }
}
```

- [ ] **Step 3: Create `viewer-app/src/styles/global.css`**

```css
@import "./tokens.css";

* {
  box-sizing: border-box;
}

html,
body,
#root {
  height: 100%;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text-primary);
  font-family: var(--font-body);
  -webkit-font-smoothing: antialiased;
}

button {
  font-family: inherit;
}

:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 4: Load the type family in `viewer-app/index.html`**

Add inside `<head>`, before the closing tag:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link
  href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap"
  rel="stylesheet"
/>
```

- [ ] **Step 5: Import global styles in `viewer-app/src/main.tsx`**

Add `import "./styles/global.css";` as the first import in `main.tsx` (alongside the existing Vite template imports).

- [ ] **Step 6: Verify the dev server renders with tokens applied**

Run: `npm run dev` (from `viewer-app/`), open the printed local URL.
Expected: background/text colors come from the token file (inspect via
devtools computed styles — `background-color` should resolve to `#f7f5f1` in
light mode or `#0c0d0f` in dark mode, not the Vite template's defaults).

- [ ] **Step 7: Commit**

```bash
cd C:/dev/ScreenTracker
git add viewer-app/package.json viewer-app/package-lock.json viewer-app/index.html viewer-app/src/main.tsx viewer-app/src/styles/tokens.css viewer-app/src/styles/global.css
git commit -m "feat: add viewer app design tokens and global styles"
```

---

### Task 10: Viewer app — session join form

**Files:**
- Create: `viewer-app/src/components/SessionJoinForm.tsx`
- Create: `viewer-app/src/components/SessionJoinForm.module.css`
- Test: `viewer-app/tests/SessionJoinForm.test.tsx`

**Interfaces:**
- Consumes: design tokens from Task 9 (via CSS custom properties, no import needed beyond the global stylesheet already loaded).
- Produces: `SessionJoinForm({ onJoin: (sessionId: string) => void })` component — consumed by Task 13's `App.tsx`. Emits a 6-character uppercase alphanumeric code, matching the signaling server's `_CODE_LENGTH = 6` (Task 2).

- [ ] **Step 1: Create `viewer-app/vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./tests/setup.ts",
  },
});
```

- [ ] **Step 2: Create `viewer-app/tests/setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 3: Add a `test` script to `viewer-app/package.json`**

Add to the `"scripts"` block: `"test": "vitest run"`

- [ ] **Step 4: Write the failing test**

`viewer-app/tests/SessionJoinForm.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SessionJoinForm } from "../src/components/SessionJoinForm";

describe("SessionJoinForm", () => {
  it("calls onJoin with the assembled code once all six digits are entered", async () => {
    const handleJoin = vi.fn();
    render(<SessionJoinForm onJoin={handleJoin} />);

    const code = "X7K2M9";
    for (let i = 0; i < code.length; i++) {
      await userEvent.type(screen.getByLabelText(`Digit ${i + 1} of 6`), code[i]);
    }
    await userEvent.click(screen.getByRole("button", { name: "Connect →" }));

    expect(handleJoin).toHaveBeenCalledWith(code);
  });

  it("disables the connect button until all six digits are filled", () => {
    render(<SessionJoinForm onJoin={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Connect →" })).toBeDisabled();
  });

  it("auto-advances focus to the next digit as you type", async () => {
    render(<SessionJoinForm onJoin={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Digit 1 of 6"), "X");
    expect(screen.getByLabelText("Digit 2 of 6")).toHaveFocus();
  });
});
```

- [ ] **Step 5: Run test to verify it fails**

Run (from `viewer-app/`): `npm test`
Expected: FAIL — `SessionJoinForm` module not found

- [ ] **Step 6: Implement `viewer-app/src/components/SessionJoinForm.module.css`**

The segmented code input is this design's signature element — six boxed
characters like a boarding-pass stub, active box marked by the accent color
on the bottom border only (no glow, no glassmorphism blur).

```css
.form {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-5);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  max-width: 360px;
  margin: var(--space-5) auto;
}

.eyebrow {
  margin: 0;
  font-family: var(--font-display);
  font-size: 0.75rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.digits {
  display: flex;
  gap: var(--space-2);
}

.digit {
  width: 40px;
  height: 48px;
  text-align: center;
  font-family: var(--font-display);
  font-size: 1.25rem;
  color: var(--text-primary);
  background: var(--bg);
  border: 1px solid var(--border);
  border-bottom: 2px solid var(--border);
  border-radius: var(--radius);
  transition: border-color var(--transition-fast);
}

.digit:focus {
  border-bottom-color: var(--accent);
  outline: none;
}

.submit {
  width: 100%;
  padding: var(--space-3);
  font-family: var(--font-display);
  font-size: 0.9rem;
  letter-spacing: 0.04em;
  color: var(--accent-contrast);
  background: var(--accent);
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.submit:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.submit:not(:disabled):hover {
  opacity: 0.85;
}

.caption {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-secondary);
}
```

- [ ] **Step 7: Implement `viewer-app/src/components/SessionJoinForm.tsx`**

```tsx
import { useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";
import styles from "./SessionJoinForm.module.css";

const CODE_LENGTH = 6;

interface SessionJoinFormProps {
  onJoin: (sessionId: string) => void;
}

export function SessionJoinForm({ onJoin }: SessionJoinFormProps) {
  const [digits, setDigits] = useState<string[]>(Array(CODE_LENGTH).fill(""));
  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);

  function handleChange(index: number, event: ChangeEvent<HTMLInputElement>) {
    const value = event.target.value.toUpperCase().slice(-1);
    if (value && !/^[A-Z0-9]$/.test(value)) return;

    const next = [...digits];
    next[index] = value;
    setDigits(next);

    if (value && index < CODE_LENGTH - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  }

  function handleKeyDown(index: number, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Backspace" && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = digits.join("");
    if (code.length === CODE_LENGTH) {
      onJoin(code);
    }
  }

  const isComplete = digits.every((digit) => digit.length === 1);

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <p className={styles.eyebrow}>Enter session code</p>
      <div className={styles.digits} role="group" aria-label="Session code">
        {digits.map((digit, index) => (
          <input
            key={index}
            ref={(el) => {
              inputRefs.current[index] = el;
            }}
            className={styles.digit}
            value={digit}
            onChange={(event) => handleChange(index, event)}
            onKeyDown={(event) => handleKeyDown(index, event)}
            maxLength={1}
            inputMode="text"
            autoCapitalize="characters"
            aria-label={`Digit ${index + 1} of ${CODE_LENGTH}`}
          />
        ))}
      </div>
      <button className={styles.submit} type="submit" disabled={!isComplete}>
        Connect →
      </button>
      <p className={styles.caption}>Your code lives on the host device.</p>
    </form>
  );
}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `npm test`
Expected: PASS (3 tests)

- [ ] **Step 9: Commit**

```bash
cd C:/dev/ScreenTracker
git add viewer-app/package.json viewer-app/package-lock.json viewer-app/vitest.config.ts viewer-app/tests/setup.ts viewer-app/src/components/SessionJoinForm.tsx viewer-app/src/components/SessionJoinForm.module.css viewer-app/tests/SessionJoinForm.test.tsx
git commit -m "feat: add segmented session code join form"
```

---

### Task 11: Viewer app — signaling socket hook

**Files:**
- Create: `viewer-app/src/hooks/useSignalingSocket.ts`
- Test: `viewer-app/tests/useSignalingSocket.test.ts`

**Interfaces:**
- Produces: `useSignalingSocket(url: string) -> { isConnected: boolean, lastMessage: SignalingMessage | null, send: (message: SignalingMessage) => void }`, type `SignalingMessage = Record<string, unknown> & { type: string }` — consumed by Task 13's `App.tsx`.

- [ ] **Step 1: Write the failing test**

`viewer-app/tests/useSignalingSocket.test.ts`:

```ts
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSignalingSocket } from "../src/hooks/useSignalingSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.onclose?.();
  }

  emitOpen() {
    this.onopen?.();
  }

  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
});

describe("useSignalingSocket", () => {
  it("reports connected once the socket opens", async () => {
    const { result } = renderHook(() => useSignalingSocket("ws://localhost/ws"));
    const socket = FakeWebSocket.instances[0];

    act(() => socket.emitOpen());

    await waitFor(() => expect(result.current.isConnected).toBe(true));
  });

  it("exposes the last parsed message", async () => {
    const { result } = renderHook(() => useSignalingSocket("ws://localhost/ws"));
    const socket = FakeWebSocket.instances[0];

    act(() => socket.emitMessage({ type: "peer-joined" }));

    await waitFor(() => expect(result.current.lastMessage).toEqual({ type: "peer-joined" }));
  });

  it("serializes messages sent through send()", () => {
    const { result } = renderHook(() => useSignalingSocket("ws://localhost/ws"));
    const socket = FakeWebSocket.instances[0];

    act(() => result.current.send({ type: "join-session", session_id: "abc" }));

    expect(socket.sent).toEqual([JSON.stringify({ type: "join-session", session_id: "abc" })]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `viewer-app/`): `npm test`
Expected: FAIL — `useSignalingSocket` module not found

- [ ] **Step 3: Implement `viewer-app/src/hooks/useSignalingSocket.ts`**

```ts
import { useCallback, useEffect, useRef, useState } from "react";

export type SignalingMessage = Record<string, unknown> & { type: string };

interface UseSignalingSocketResult {
  isConnected: boolean;
  lastMessage: SignalingMessage | null;
  send: (message: SignalingMessage) => void;
}

export function useSignalingSocket(url: string): UseSignalingSocketResult {
  const socketRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<SignalingMessage | null>(null);

  useEffect(() => {
    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => setIsConnected(true);
    socket.onclose = () => setIsConnected(false);
    socket.onmessage = (event) => {
      setLastMessage(JSON.parse(event.data) as SignalingMessage);
    };

    return () => socket.close();
  }, [url]);

  const send = useCallback((message: SignalingMessage) => {
    socketRef.current?.send(JSON.stringify(message));
  }, []);

  return { isConnected, lastMessage, send };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd C:/dev/ScreenTracker
git add viewer-app/src/hooks/useSignalingSocket.ts viewer-app/tests/useSignalingSocket.test.ts
git commit -m "feat: add viewer app signaling socket hook"
```

---

### Task 12: Viewer app — WebRTC viewer hook and video player

**Files:**
- Create: `viewer-app/src/hooks/useWebRTCViewer.ts`
- Create: `viewer-app/src/components/VideoPlayer.tsx`
- Create: `viewer-app/src/components/VideoPlayer.module.css`
- Test: `viewer-app/tests/VideoPlayer.test.tsx`

**Interfaces:**
- Produces: `useWebRTCViewer({ onIceCandidate: (candidate: RTCIceCandidate) => void }) -> { remoteStream: MediaStream | null, handleOffer: (sdp: string) => Promise<string>, handleRemoteIceCandidate: (candidate: RTCIceCandidateInit) => Promise<void> }`; `VideoPlayer({ stream: MediaStream | null })` component — both consumed by Task 13's `App.tsx`.

- [ ] **Step 1: Implement `viewer-app/src/hooks/useWebRTCViewer.ts`**

(No isolated unit test here — it wraps the browser's real `RTCPeerConnection`, which jsdom doesn't implement; it's exercised through `App.test.tsx` in Task 13 with a stub `RTCPeerConnection`.)

```ts
import { useEffect, useRef, useState } from "react";

interface UseWebRTCViewerOptions {
  onIceCandidate: (candidate: RTCIceCandidate) => void;
}

interface UseWebRTCViewerResult {
  remoteStream: MediaStream | null;
  handleOffer: (sdp: string) => Promise<string>;
  handleRemoteIceCandidate: (candidate: RTCIceCandidateInit) => Promise<void>;
}

export function useWebRTCViewer({
  onIceCandidate,
}: UseWebRTCViewerOptions): UseWebRTCViewerResult {
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);

  useEffect(() => {
    const pc = new RTCPeerConnection();
    pcRef.current = pc;

    pc.ontrack = (event) => setRemoteStream(event.streams[0]);
    pc.onicecandidate = (event) => {
      if (event.candidate) onIceCandidate(event.candidate);
    };

    return () => pc.close();
  }, [onIceCandidate]);

  async function handleOffer(sdp: string): Promise<string> {
    const pc = pcRef.current;
    if (!pc) throw new Error("Peer connection not ready");
    await pc.setRemoteDescription({ type: "offer", sdp });
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    if (!pc.localDescription) throw new Error("Failed to create local description");
    return pc.localDescription.sdp;
  }

  async function handleRemoteIceCandidate(candidate: RTCIceCandidateInit): Promise<void> {
    await pcRef.current?.addIceCandidate(candidate);
  }

  return { remoteStream, handleOffer, handleRemoteIceCandidate };
}
```

- [ ] **Step 2: Write the failing test for `VideoPlayer`**

`viewer-app/tests/VideoPlayer.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VideoPlayer } from "../src/components/VideoPlayer";

describe("VideoPlayer", () => {
  it("shows a waiting message when there is no stream", () => {
    render(<VideoPlayer stream={null} />);
    expect(screen.getByText(/waiting for host/i)).toBeInTheDocument();
  });

  it("renders a video element bound to the stream when present", () => {
    const fakeStream = {} as MediaStream;
    const { container } = render(<VideoPlayer stream={fakeStream} />);
    expect(container.querySelector("video")).not.toBeNull();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `viewer-app/`): `npm test`
Expected: FAIL — `VideoPlayer` module not found

- [ ] **Step 4: Implement `viewer-app/src/components/VideoPlayer.module.css`**

```css
.waiting {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  font-family: var(--font-display);
  font-size: 0.9rem;
}

.video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: var(--bg);
}
```

- [ ] **Step 5: Implement `viewer-app/src/components/VideoPlayer.tsx`**

```tsx
import { useEffect, useRef } from "react";
import styles from "./VideoPlayer.module.css";

interface VideoPlayerProps {
  stream: MediaStream | null;
}

export function VideoPlayer({ stream }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  if (!stream) {
    return <p className={styles.waiting}>Waiting for host to start streaming…</p>;
  }

  return <video className={styles.video} ref={videoRef} autoPlay playsInline />;
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `npm test`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
cd C:/dev/ScreenTracker
git add viewer-app/src/hooks/useWebRTCViewer.ts viewer-app/src/components/VideoPlayer.tsx viewer-app/src/components/VideoPlayer.module.css viewer-app/tests/VideoPlayer.test.tsx
git commit -m "feat: add viewer app WebRTC hook and video player"
```

---

### Task 13: Viewer app — wire up App.tsx with top bar and error states

**Files:**
- Modify: `viewer-app/src/App.tsx`
- Create: `viewer-app/src/App.module.css`
- Test: `viewer-app/tests/App.test.tsx`

**Interfaces:**
- Consumes: `SessionJoinForm` (Task 10), `useSignalingSocket`/`SignalingMessage` (Task 11), `useWebRTCViewer` (Task 12), `VideoPlayer` (Task 12).
- Produces: `App` component — the viewer app's root, not consumed by any other task.

- [ ] **Step 1: Write the failing test**

`viewer-app/tests/App.test.tsx`:

```tsx
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {}

  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

class FakeRTCPeerConnection {
  onicecandidate: unknown;
  ontrack: unknown;
  close() {}
}

async function joinWithCode(code: string) {
  for (let i = 0; i < code.length; i++) {
    await userEvent.type(screen.getByLabelText(`Digit ${i + 1} of 6`), code[i]);
  }
  await userEvent.click(screen.getByRole("button", { name: "Connect →" }));
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  vi.stubGlobal("RTCPeerConnection", FakeRTCPeerConnection as unknown as typeof RTCPeerConnection);
});

describe("App", () => {
  it("shows a human-readable error when the session has expired", async () => {
    render(<App />);
    await joinWithCode("X7K2M9");

    const socket = FakeWebSocket.instances[0];
    act(() => socket.emitMessage({ type: "session-expired", reason: "expired" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This session code has expired."
    );
  });

  it("shows a human-readable error when the host disconnects", async () => {
    render(<App />);
    await joinWithCode("X7K2M9");

    const socket = FakeWebSocket.instances[0];
    act(() => socket.emitMessage({ type: "peer-disconnected" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Host disconnected.");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `viewer-app/`): `npm test`
Expected: FAIL — current `App.tsx` (Vite template default) has none of this behavior

- [ ] **Step 3: Implement `viewer-app/src/App.module.css`**

Top bar carries the wordmark and a status indicator; the `LIVE` dot is the
second half of the design's signature moment (segmented code input to get
in, breathing dot once connected) — a slow opacity pulse, not a glow/blur
effect, and inert under `prefers-reduced-motion` (handled globally in
`global.css`).

```css
.shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.topBar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
}

.wordmark {
  font-family: var(--font-display);
  font-size: 0.9rem;
  letter-spacing: 0.06em;
}

.status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-family: var(--font-display);
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-secondary);
}

.dotLive {
  background: var(--accent);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

.main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.error {
  margin-top: var(--space-3);
  font-size: 0.85rem;
  color: var(--accent);
  border-left: 2px solid var(--accent);
  padding-left: var(--space-2);
}
```

- [ ] **Step 4: Implement `viewer-app/src/App.tsx`**

```tsx
import { useCallback, useEffect, useState } from "react";
import { SessionJoinForm } from "./components/SessionJoinForm";
import { VideoPlayer } from "./components/VideoPlayer";
import { useSignalingSocket } from "./hooks/useSignalingSocket";
import { useWebRTCViewer } from "./hooks/useWebRTCViewer";
import styles from "./App.module.css";

const SIGNALING_SERVER_URL = import.meta.env.VITE_SIGNALING_SERVER_URL as string;

type ViewerStatus = "idle" | "joining" | "streaming" | "error";

export function App() {
  const [status, setStatus] = useState<ViewerStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const { send, lastMessage } = useSignalingSocket(SIGNALING_SERVER_URL);

  const handleIceCandidate = useCallback(
    (candidate: RTCIceCandidate) => {
      send({ type: "ice-candidate", candidate: candidate.toJSON() });
    },
    [send]
  );

  const { remoteStream, handleOffer, handleRemoteIceCandidate } = useWebRTCViewer({
    onIceCandidate: handleIceCandidate,
  });

  useEffect(() => {
    if (!lastMessage) return;

    switch (lastMessage.type) {
      case "offer":
        void handleOffer(lastMessage.sdp as string).then((answerSdp) => {
          send({ type: "answer", sdp: answerSdp });
          setStatus("streaming");
        });
        break;
      case "ice-candidate":
        void handleRemoteIceCandidate(lastMessage.candidate as RTCIceCandidateInit);
        break;
      case "session-expired":
        setStatus("error");
        setErrorMessage(
          lastMessage.reason === "expired"
            ? "This session code has expired."
            : "Session code not found."
        );
        break;
      case "peer-disconnected":
        setStatus("error");
        setErrorMessage("Host disconnected.");
        break;
    }
  }, [lastMessage, handleOffer, handleRemoteIceCandidate, send]);

  function handleJoin(sessionId: string) {
    setStatus("joining");
    setErrorMessage(null);
    send({ type: "join-session", session_id: sessionId });
  }

  return (
    <div className={styles.shell}>
      <header className={styles.topBar}>
        <span className={styles.wordmark}>ScreenTracker</span>
        <span className={styles.status}>
          <span className={status === "streaming" ? `${styles.dot} ${styles.dotLive}` : styles.dot} />
          {status === "streaming" ? "LIVE" : status}
        </span>
      </header>
      <main className={styles.main}>
        {status !== "streaming" && <SessionJoinForm onJoin={handleJoin} />}
        {errorMessage && (
          <p className={styles.error} role="alert">
            {errorMessage}
          </p>
        )}
        {status === "streaming" && <VideoPlayer stream={remoteStream} />}
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the full viewer test suite**

Run: `npm test`
Expected: all viewer-app tests (Tasks 10–13) PASS

- [ ] **Step 7: Commit**

```bash
cd C:/dev/ScreenTracker
git add viewer-app/src/App.tsx viewer-app/src/App.module.css viewer-app/tests/App.test.tsx
git commit -m "feat: wire up viewer app with top bar, session join and error states"
```

---

### Task 14: TURN server infrastructure

**Files:**
- Create: `infra/coturn/turnserver.conf`
- Create: `infra/coturn/README.md`

**Interfaces:** None — infrastructure config, not imported by any app code. Consumed manually during deployment (Task 14).

- [ ] **Step 1: Create `infra/coturn/turnserver.conf`**

```
listening-port=3478
tls-listening-port=5349
fingerprint
lt-cred-mech
user=screentracker:CHANGE_ME_STRONG_PASSWORD
realm=screentracker.local
total-quota=100
stale-nonce=600
no-multicast-peers
no-cli
```

- [ ] **Step 2: Create `infra/coturn/README.md`**

```md
# TURN server (coturn)

Relays media when a direct peer-to-peer connection between host and viewer
can't be established (common when either side is behind restrictive NAT).
Needs a persistent UDP port, so it's deployed to a small Azure VM or
Container Instance — not App Service.

## Deploy (Azure Container Instance, matches the $0/month constraint)

1. Replace `CHANGE_ME_STRONG_PASSWORD` in `turnserver.conf` with a generated
   secret; put the same value in `.env` as `TURN_PASSWORD`.
2. Create the container group in an Azure-for-Students-allowed region:

\`\`\`bash
az container create \
  --resource-group rg-screentracker \
  --name screentracker-turn \
  --image coturn/coturn:latest \
  --ports 3478 5349 \
  --protocol UDP \
  --command-line "turnserver -c /etc/coturn/turnserver.conf" \
  --azure-file-volume-share-name coturn-config \
  --azure-file-volume-mount-path /etc/coturn
\`\`\`

3. Copy `turnserver.conf` into the mounted file share before starting the
   container (Azure Portal → Storage account → File share → Upload).

## Verify

Use the WebRTC sample Trickle ICE tester
(`https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/`)
with a `turn:` URI pointing at the container's public IP, port 3478, and the
credentials from step 1. A successful `relay` candidate confirms the TURN
server is reachable and authenticating correctly.
```

- [ ] **Step 3: Commit**

```bash
cd C:/dev/ScreenTracker
git add infra/coturn/turnserver.conf infra/coturn/README.md
git commit -m "chore: add coturn TURN server config and deployment docs"
```

---

### Task 15: End-to-end verification and Definition of Done

**Files:** none created — this task verifies the system built in Tasks 1–13 and updates `HANDOFF.md`.

**Interfaces:** none — manual verification only.

- [ ] **Step 1: Deploy the signaling server**

Deploy `signaling-server/` (Task 4's Dockerfile) to the Azure App Service created earlier, using an Azure-for-Students-allowed region and the **F1 (Free)** or **B1 (Basic)** plan. Set `SIGNALING_SERVER_URL` / `VITE_SIGNALING_SERVER_URL` in both `.env` and the viewer app's build-time env to the deployed `wss://` URL.

- [ ] **Step 2: Deploy the TURN server**

Follow `infra/coturn/README.md`. Confirm the Trickle ICE test in that README returns a `relay` candidate before proceeding — a broken TURN server only reveals itself later, as a viewer on mobile data that simply never gets video.

- [ ] **Step 3: Run the host app**

On the PC, with `SIGNALING_SERVER_URL` pointed at the deployed signaling server: `python -m screentracker_host.main`. Note the printed session code.

- [ ] **Step 4: Run the viewer on a different network**

Build and serve `viewer-app/` (`npm run build && npm run preview`, or deploy it as a static site), open it from a phone on mobile data (a different network than the host's), enter the session code.
Expected: video of the host's screen appears within a few seconds.

- [ ] **Step 5: Verify error paths manually**

- Enter a made-up session code → expect "Session code not found."
- Join successfully, then stop the host app (Ctrl+C) → viewer should show "Host disconnected."
- Wait 5+ minutes after creating a session before joining → expect "This session code has expired."

- [ ] **Step 6: Run every automated test suite**

```bash
cd C:/dev/ScreenTracker/signaling-server && pytest -v
cd ../host-app && pytest -v
cd ../viewer-app && npm test
```

Expected: all PASS.

- [ ] **Step 7: Definition of Done checklist** (standard §18)

- [ ] Code was actually run and observed working (Steps 1–5 above)
- [ ] Relevant tests written and passing (Step 6)
- [ ] `code-review` skill run over the branch
- [ ] Docs updated in the same PR (`README.md`, `docs/architecture.md`, `docs/api-spec.md` already current from Task 1; update if anything drifted during implementation)
- [ ] No schema/migration involved (no database in Phase 1)
- [ ] `HANDOFF.md` updated (Step 8)
- [ ] No new secret/config var without a matching `.env.example` entry
- [ ] Commit messages follow the standard, no AI co-author trailer

- [ ] **Step 8: Update `HANDOFF.md`**

Rewrite `HANDOFF.md` to reflect Phase 1 completion:

```md
# Handoff — ScreenTracker
Son güncelleme: <doldurulacak tarih/saat>, güncelleyen: <ajan adı>

## Şu an ne yapılıyor
Faz 1 (MVP) tamamlandı: host ekranını farklı ağdaki bir viewer'dan canlı izleyebiliyoruz.

## Sıradaki somut adım
Faz 2 (input kontrolü) için ayrı bir brainstorming/spec turu başlat.

## Bilinmesi gerekenler
- TURN sunucusu doğrulaması Trickle ICE testiyle yapıldı, relay candidate alınıyor
- Uçtan uca WebRTC bağlantısı otomatikleştirilmiş testi yok, manuel doğrulama gerekiyor (bkz. plan Task 15)

## İlgili dosyalar
- docs/superpowers/specs/2026-08-17-remote-screen-view-design.md
- docs/superpowers/plans/2026-08-17-screentracker-mvp.md

## Son 3 commit
- <git log --oneline -3 çıktısını buraya yapıştır>
```

- [ ] **Step 9: Commit**

```bash
cd C:/dev/ScreenTracker
git add HANDOFF.md
git commit -m "docs: update HANDOFF.md after Phase 1 completion"
```
