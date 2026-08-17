# Device Pairing & Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the project owner approve which devices can ever connect to their host — first connection requires an interactive terminal approval, approved devices reconnect automatically forever after with no code entry — and document Tailscale as the tested, primary way to make ScreenTracker reachable from anywhere.

**Architecture:** A `host_id` (persistent, independent of the ephemeral session code) lets a previously-approved device look up its owner's current session without typing a code. The signaling server gains a `register-host` message, a `host_id → connection_id` lookup, and generic relay support for three new host-originated messages (`pair-approved`/`pair-rejected`/`authenticate-failed`) reusing the existing peer-relay mechanism. The host app persists two small JSON files (`host_identity.json`, `paired_devices.json`) and gates unknown devices behind a blocking-but-non-event-loop-blocking terminal prompt. The viewer stores its device id and any granted token in `localStorage` and attempts silent auto-authentication before ever showing the code-entry form.

**Tech Stack:** Same as Phase 1 — Python (FastAPI, aiortc), TypeScript/React (Vite).

**Spec:** `docs/superpowers/specs/2026-08-17-device-pairing-and-deployment.md`

## Global Constraints

- `host_identity.json` and `paired_devices.json` live in `host-app/`, are gitignored, never committed
- Pairing approval prompt times out after 60 seconds (spec §4)
- Rejected/timed-out pairing releases the session's viewer slot so the code (or a retry) still works for someone else
- The signaling server stays stateless/ephemeral — the `host_id → connection_id` map is in-memory only, matching every other piece of server state
- Existing `join-session` wire format must stay backward compatible — `device_id` is an optional addition, not a breaking change
- Code, identifiers, and commit messages: English. Conventional Commits, imperative mood, no AI co-author trailer — ever
- Every backend change ships with a test; host-app's `main.py` orchestration stays manual-smoke-test-only per existing project convention, **except** newly-decomposed testable functions (e.g. `_handle_peer_joined`), which do get unit tests
- Documentation for untested deployment paths (Azure, tunnel services) must explicitly say so and point readers to opening an issue or forking

---

## File Structure

```
signaling-server/
├── app/
│   ├── models.py           # + RegisterHostMessage, AuthenticateMessage,
│   │                         PairApprovedMessage, PairRejectedMessage,
│   │                         AuthenticateFailedMessage, ReleasePeerMessage;
│   │                         JoinSessionMessage gets optional device_id
│   ├── session_manager.py  # + release_viewer()
│   └── main.py             # + register-host handling, authenticate handling,
│                              release-peer handling, relay extended to the
│                              3 new host→viewer message types
├── tests/
│   ├── test_models.py      # + new message parsing tests
│   ├── test_session_manager.py  # + release_viewer test
│   └── test_main.py        # + register-host/authenticate/pairing-reject flow tests
host-app/
├── screentracker_host/
│   ├── host_identity.py    # new: persistent host_id
│   ├── paired_devices.py   # new: persistent device→token store
│   ├── pairing.py          # new: async terminal approval prompt with timeout
│   └── main.py             # rewired: register-host, peer-joined branches on
│                              token/device_id, loop no longer exits on a
│                              pre-stream disconnect
├── tests/
│   ├── test_host_identity.py   # new
│   ├── test_paired_devices.py  # new
│   ├── test_pairing.py         # new
│   └── test_main.py            # new: _handle_peer_joined unit tests
viewer-app/
├── src/
│   ├── deviceIdentity.ts   # new: device_id + stored-pairing localStorage helpers
│   └── App.tsx             # rewired: auto-authenticate on load, pairing states
├── tests/
│   ├── deviceIdentity.test.ts  # new
│   └── App.test.tsx            # + pairing flow tests
docs/
├── deployment.md           # new: Tailscale (tested) + Azure/tunnel (untested) guide
├── api-spec.md             # + new message types
└── architecture.md         # + decisions log entries
```

---

### Task 1: Signaling server — message models for pairing

**Files:**
- Modify: `signaling-server/app/models.py`
- Test: `signaling-server/tests/test_models.py`

**Interfaces:**
- Produces: `RegisterHostMessage(host_id: str)`, `JoinSessionMessage(session_id: str, device_id: str | None = None)` (extended), `AuthenticateMessage(host_id: str, device_id: str, token: str)`, `PairApprovedMessage(token: str, host_id: str)`, `PairRejectedMessage(reason: str)`, `AuthenticateFailedMessage()`, `ReleasePeerMessage()` — consumed by Task 2's `main.py`.

- [ ] **Step 1: Write the failing tests**

Add to `signaling-server/tests/test_models.py`:

```python
from app.models import (
    AuthenticateMessage,
    JoinSessionMessage,
    PairApprovedMessage,
    PairRejectedMessage,
    ReleasePeerMessage,
    parse_inbound_message,
)


def test_parse_join_session_message_without_device_id():
    parsed = parse_inbound_message({"type": "join-session", "session_id": "abc123"})
    assert isinstance(parsed, JoinSessionMessage)
    assert parsed.device_id is None


def test_parse_join_session_message_with_device_id():
    parsed = parse_inbound_message(
        {"type": "join-session", "session_id": "abc123", "device_id": "dev-1"}
    )
    assert isinstance(parsed, JoinSessionMessage)
    assert parsed.device_id == "dev-1"


def test_parse_register_host_message():
    parsed = parse_inbound_message({"type": "register-host", "host_id": "host-1"})
    assert parsed.host_id == "host-1"


def test_parse_authenticate_message():
    parsed = parse_inbound_message(
        {"type": "authenticate", "host_id": "host-1", "device_id": "dev-1", "token": "tok-1"}
    )
    assert isinstance(parsed, AuthenticateMessage)
    assert parsed.host_id == "host-1"
    assert parsed.device_id == "dev-1"
    assert parsed.token == "tok-1"


def test_parse_pair_approved_message():
    parsed = parse_inbound_message(
        {"type": "pair-approved", "token": "tok-1", "host_id": "host-1"}
    )
    assert isinstance(parsed, PairApprovedMessage)


def test_parse_pair_rejected_message():
    parsed = parse_inbound_message({"type": "pair-rejected", "reason": "denied"})
    assert isinstance(parsed, PairRejectedMessage)


def test_parse_release_peer_message():
    parsed = parse_inbound_message({"type": "release-peer"})
    assert isinstance(parsed, ReleasePeerMessage)
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `signaling-server/`): `python -m pytest tests/test_models.py -v`
Expected: FAIL — new message types/fields don't exist yet

- [ ] **Step 3: Implement the model additions**

In `signaling-server/app/models.py`, modify `JoinSessionMessage` and add the new classes (keep every existing class as-is):

```python
class JoinSessionMessage(BaseModel):
    type: Literal["join-session"] = "join-session"
    session_id: str
    device_id: str | None = None


class RegisterHostMessage(BaseModel):
    type: Literal["register-host"] = "register-host"
    host_id: str


class AuthenticateMessage(BaseModel):
    type: Literal["authenticate"] = "authenticate"
    host_id: str
    device_id: str
    token: str


class PairApprovedMessage(BaseModel):
    type: Literal["pair-approved"] = "pair-approved"
    token: str
    host_id: str


class PairRejectedMessage(BaseModel):
    type: Literal["pair-rejected"] = "pair-rejected"
    reason: str


class AuthenticateFailedMessage(BaseModel):
    type: Literal["authenticate-failed"] = "authenticate-failed"


class ReleasePeerMessage(BaseModel):
    type: Literal["release-peer"] = "release-peer"
```

Update `InboundMessage`, add every new type to `_INBOUND_MODELS`:

```python
InboundMessage = Union[
    CreateSessionMessage,
    JoinSessionMessage,
    SdpMessage,
    IceCandidateMessage,
    RegisterHostMessage,
    AuthenticateMessage,
    PairApprovedMessage,
    PairRejectedMessage,
    AuthenticateFailedMessage,
    ReleasePeerMessage,
]

_INBOUND_MODELS: dict[str, type[BaseModel]] = {
    "create-session": CreateSessionMessage,
    "join-session": JoinSessionMessage,
    "offer": SdpMessage,
    "answer": SdpMessage,
    "ice-candidate": IceCandidateMessage,
    "register-host": RegisterHostMessage,
    "authenticate": AuthenticateMessage,
    "pair-approved": PairApprovedMessage,
    "pair-rejected": PairRejectedMessage,
    "authenticate-failed": AuthenticateFailedMessage,
    "release-peer": ReleasePeerMessage,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (all tests, old and new)

- [ ] **Step 5: Commit**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp/signaling-server
git add app/models.py tests/test_models.py
git commit -m "feat: add device pairing message models"
```

---

### Task 2: Signaling server — host registry, release_viewer, and main.py wiring

**Files:**
- Modify: `signaling-server/app/session_manager.py`
- Modify: `signaling-server/app/main.py`
- Test: `signaling-server/tests/test_session_manager.py`
- Test: `signaling-server/tests/test_main.py`

**Interfaces:**
- Consumes: models from Task 1.
- Produces: `SessionManager.release_viewer(session_id: str) -> None` — consumed by `main.py`'s `release-peer` handler.

- [ ] **Step 1: Write the failing session_manager test**

Add to `signaling-server/tests/test_session_manager.py`:

```python
def test_release_viewer_clears_the_claim_so_a_new_join_succeeds():
    manager = SessionManager()
    session = manager.create_session(host_connection_id="host-1")
    manager.join_session(session.session_id, viewer_connection_id="viewer-1")

    manager.release_viewer(session.session_id)

    rejoined = manager.join_session(session.session_id, viewer_connection_id="viewer-2")
    assert rejoined.viewer_connection_id == "viewer-2"


def test_release_viewer_on_unknown_session_is_a_no_op():
    manager = SessionManager()
    manager.release_viewer("does-not-exist")  # must not raise
```

- [ ] **Step 2: Run to verify RED**

Run (from `signaling-server/`): `python -m pytest tests/test_session_manager.py -v`
Expected: FAIL — `release_viewer` doesn't exist

- [ ] **Step 3: Implement `release_viewer`**

Add to `signaling-server/app/session_manager.py`'s `SessionManager` class:

```python
    def release_viewer(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.viewer_connection_id = None
```

- [ ] **Step 4: Run to verify GREEN**

Run: `python -m pytest tests/test_session_manager.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing main.py integration tests**

Add to `signaling-server/tests/test_main.py`:

```python
def test_authenticate_with_valid_token_joins_without_a_code():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws:
        host_ws.send_json({"type": "register-host", "host_id": "host-abc"})
        host_ws.send_json({"type": "create-session"})
        host_ws.receive_json()  # session-created, session_id not needed here

        with client.websocket_connect("/ws") as viewer_ws:
            viewer_ws.send_json(
                {
                    "type": "authenticate",
                    "host_id": "host-abc",
                    "device_id": "dev-1",
                    "token": "tok-1",
                }
            )
            peer_joined = host_ws.receive_json()
            assert peer_joined["type"] == "peer-joined"
            assert peer_joined["device_id"] == "dev-1"
            assert peer_joined["token"] == "tok-1"


def test_authenticate_with_unknown_host_id_returns_not_found():
    client = TestClient(app)
    with client.websocket_connect("/ws") as viewer_ws:
        viewer_ws.send_json(
            {
                "type": "authenticate",
                "host_id": "no-such-host",
                "device_id": "dev-1",
                "token": "tok-1",
            }
        )
        response = viewer_ws.receive_json()
        assert response == {"type": "session-expired", "reason": "not-found"}


def test_join_session_relays_device_id_in_peer_joined():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect("/ws") as viewer_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        viewer_ws.send_json(
            {"type": "join-session", "session_id": session_id, "device_id": "dev-2"}
        )
        peer_joined = host_ws.receive_json()
        assert peer_joined == {"type": "peer-joined", "device_id": "dev-2", "token": None}


def test_pair_approved_pair_rejected_and_authenticate_failed_relay_to_viewer():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect("/ws") as viewer_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]
        viewer_ws.send_json(
            {"type": "join-session", "session_id": session_id, "device_id": "dev-3"}
        )
        host_ws.receive_json()  # peer-joined

        host_ws.send_json({"type": "pair-approved", "token": "tok-9", "host_id": "host-xyz"})
        assert viewer_ws.receive_json() == {
            "type": "pair-approved",
            "token": "tok-9",
            "host_id": "host-xyz",
        }


def test_release_peer_frees_the_slot_for_a_new_joiner():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect(
        "/ws"
    ) as first_viewer_ws, client.websocket_connect("/ws") as second_viewer_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        first_viewer_ws.send_json(
            {"type": "join-session", "session_id": session_id, "device_id": "dev-4"}
        )
        host_ws.receive_json()  # peer-joined for the first viewer

        host_ws.send_json({"type": "pair-rejected", "reason": "denied"})
        assert first_viewer_ws.receive_json() == {"type": "pair-rejected", "reason": "denied"}
        host_ws.send_json({"type": "release-peer"})

        second_viewer_ws.send_json(
            {"type": "join-session", "session_id": session_id, "device_id": "dev-5"}
        )
        peer_joined = host_ws.receive_json()
        assert peer_joined == {"type": "peer-joined", "device_id": "dev-5", "token": None}
```

- [ ] **Step 6: Run to verify RED**

Run (from `signaling-server/`): `python -m pytest tests/test_main.py -v`
Expected: FAIL — `register-host`/`authenticate`/`release-peer` unhandled, `peer-joined` payload doesn't include `device_id`/`token` yet

- [ ] **Step 7: Implement the `main.py` changes**

Replace the full contents of `signaling-server/app/main.py`:

```python
import logging
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.models import parse_inbound_message
from app.rate_limiter import RateLimiter
from app.session_manager import (
    SessionAlreadyClaimedError,
    SessionExpiredError,
    SessionManager,
    SessionNotFoundError,
)

logger = logging.getLogger(__name__)

app = FastAPI()
session_manager = SessionManager()
rate_limiter = RateLimiter()

# connection_id -> WebSocket, so relayed messages reach the right peer
_connections: dict[str, WebSocket] = {}
# connection_id -> session_id, so a disconnect can find the peer to notify
_connection_sessions: dict[str, str] = {}
# host_id -> connection_id, so a returning paired device can find its host's
# current session without ever typing a code
_host_ids: dict[str, str] = {}

_RELAYED_MESSAGE_TYPES = (
    "offer",
    "answer",
    "ice-candidate",
    "pair-approved",
    "pair-rejected",
    "authenticate-failed",
)


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
            except ValueError as error:
                logger.warning(
                    "Discarding unparseable message from %s: %s (raw=%r)",
                    connection_id,
                    error,
                    raw,
                )
                continue

            if message.type == "create-session":
                session = session_manager.create_session(connection_id)
                _connection_sessions[connection_id] = session.session_id
                await websocket.send_json(
                    {"type": "session-created", "session_id": session.session_id}
                )
            elif message.type == "register-host":
                _host_ids[message.host_id] = connection_id
            elif message.type == "join-session":
                await _handle_join(connection_id, message.session_id, message.device_id, websocket)
            elif message.type == "authenticate":
                await _handle_authenticate(connection_id, message, websocket)
            elif message.type == "release-peer":
                _handle_release_peer(connection_id)
            elif message.type in _RELAYED_MESSAGE_TYPES:
                await _relay_to_peer(connection_id, raw)
    except WebSocketDisconnect:
        await _handle_disconnect(connection_id)
    except Exception:
        # Catch any other exception (e.g., JSON decode errors, transport exceptions)
        # to ensure cleanup always happens and peer is notified
        logger.exception("Connection %s failed; cleaning up", connection_id)
        await _handle_disconnect(connection_id)


async def _handle_join(
    connection_id: str, session_id: str, device_id: str | None, websocket: WebSocket
) -> None:
    client_key = _rate_limit_key(websocket)

    if not await _claim_session(session_id, connection_id, client_key, websocket):
        return

    _connection_sessions[connection_id] = session_id
    session = session_manager.get_session(session_id)
    host_ws = _connections.get(session.host_connection_id) if session else None
    if host_ws is not None:
        await host_ws.send_json(
            {"type": "peer-joined", "device_id": device_id, "token": None}
        )


async def _handle_authenticate(connection_id: str, message, websocket: WebSocket) -> None:
    client_key = _rate_limit_key(websocket)

    if rate_limiter.seconds_until_unlocked(client_key) > 0:
        await _handle_join_failure(websocket, client_key, "rate-limited")
        return

    host_connection_id = _host_ids.get(message.host_id)
    session_id = _connection_sessions.get(host_connection_id) if host_connection_id else None
    if session_id is None:
        await _handle_join_failure(websocket, client_key, "not-found")
        return

    if not await _claim_session(session_id, connection_id, client_key, websocket):
        return

    _connection_sessions[connection_id] = session_id
    host_ws = _connections.get(host_connection_id)
    if host_ws is not None:
        await host_ws.send_json(
            {
                "type": "peer-joined",
                "device_id": message.device_id,
                "token": message.token,
            }
        )


async def _claim_session(
    session_id: str, connection_id: str, client_key: str, websocket: WebSocket
) -> bool:
    """Try to claim session_id for connection_id. Sends the appropriate
    session-expired reply and records a rate-limit failure on any rejection.
    Returns True only if the claim succeeded."""
    try:
        session_manager.join_session(session_id, connection_id)
    except SessionNotFoundError:
        await _handle_join_failure(websocket, client_key, "not-found")
        return False
    except SessionExpiredError:
        await _handle_join_failure(websocket, client_key, "expired")
        return False
    except SessionAlreadyClaimedError:
        await _handle_join_failure(websocket, client_key, "already-claimed")
        return False

    rate_limiter.record_success(client_key)
    return True


async def _handle_join_failure(websocket: WebSocket, client_key: str, reason: str) -> None:
    rate_limiter.record_failure(client_key)
    message: dict[str, str | float] = {"type": "session-expired", "reason": reason}
    seconds_locked = rate_limiter.seconds_until_unlocked(client_key)
    if seconds_locked > 0:
        message["retry_after_seconds"] = round(seconds_locked, 1)
    await websocket.send_json(message)
    if rate_limiter.should_kick(client_key):
        logger.warning("Closing connection from %s after repeated failed join attempts", client_key)
        await websocket.close()


def _handle_release_peer(connection_id: str) -> None:
    session_id = _connection_sessions.get(connection_id)
    if session_id is not None:
        session_manager.release_viewer(session_id)


def _rate_limit_key(websocket: WebSocket) -> str:
    client = websocket.client
    return client.host if client is not None else "unknown"


async def _relay_to_peer(connection_id: str, raw: dict) -> None:
    peer_ws = _peer_websocket_for(connection_id)
    if peer_ws is not None:
        await peer_ws.send_json(raw)


async def _handle_disconnect(connection_id: str) -> None:
    peer_ws = _peer_websocket_for(connection_id)
    session_id = _connection_sessions.pop(connection_id, None)
    _connections.pop(connection_id, None)
    for host_id, mapped_connection_id in list(_host_ids.items()):
        if mapped_connection_id == connection_id:
            del _host_ids[host_id]

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

- [ ] **Step 8: Run to verify GREEN**

Run: `python -m pytest tests/test_main.py -v`
Expected: PASS (all tests, old and new)

- [ ] **Step 9: Run the full signaling-server suite**

Run: `python -m pytest -v`
Expected: all tests pass (no regressions in `test_rate_limiter.py`, `test_wire_contract.py`, etc.)

- [ ] **Step 10: Commit**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp/signaling-server
git add app/session_manager.py app/main.py tests/test_session_manager.py tests/test_main.py
git commit -m "feat: add host registry, authenticate flow, and peer release to signaling server"
```

---

### Task 3: Host app — persistent host identity

**Files:**
- Create: `host-app/screentracker_host/host_identity.py`
- Test: `host-app/tests/test_host_identity.py`
- Modify: `host-app/.gitignore` (create if it doesn't exist) — add `host_identity.json`, `paired_devices.json`

**Interfaces:**
- Produces: `load_or_create_host_id(path: Path = DEFAULT_PATH) -> str` — consumed by Task 6's `main.py`.

- [ ] **Step 1: Write the failing test**

`host-app/tests/test_host_identity.py`:

```python
import json

from screentracker_host.host_identity import load_or_create_host_id


def test_creates_a_new_host_id_when_the_file_does_not_exist(tmp_path):
    path = tmp_path / "host_identity.json"

    host_id = load_or_create_host_id(path)

    assert host_id
    assert json.loads(path.read_text())["host_id"] == host_id


def test_returns_the_same_host_id_on_subsequent_calls(tmp_path):
    path = tmp_path / "host_identity.json"

    first = load_or_create_host_id(path)
    second = load_or_create_host_id(path)

    assert first == second
```

- [ ] **Step 2: Run to verify RED**

Run (from `host-app/`): `./venv/Scripts/python.exe -m pytest tests/test_host_identity.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement `host_identity.py`**

```python
import json
import secrets
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent.parent / "host_identity.json"


def load_or_create_host_id(path: Path = DEFAULT_PATH) -> str:
    if path.exists():
        return json.loads(path.read_text())["host_id"]
    host_id = secrets.token_urlsafe(16)
    path.write_text(json.dumps({"host_id": host_id}))
    return host_id
```

- [ ] **Step 4: Run to verify GREEN**

Run: `./venv/Scripts/python.exe -m pytest tests/test_host_identity.py -v`
Expected: PASS

- [ ] **Step 5: Add gitignore entries**

Create or append to `host-app/.gitignore`:

```
host_identity.json
paired_devices.json
```

- [ ] **Step 6: Commit**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp/host-app
git add screentracker_host/host_identity.py tests/test_host_identity.py .gitignore
git commit -m "feat: add persistent host identity"
```

---

### Task 4: Host app — persistent paired device store

**Files:**
- Create: `host-app/screentracker_host/paired_devices.py`
- Test: `host-app/tests/test_paired_devices.py`

**Interfaces:**
- Produces: `PairedDevices(path: Path = DEFAULT_PATH)` with `is_paired(device_id: str, token: str) -> bool`, `is_known(device_id: str) -> bool`, `approve(device_id: str, label: str) -> str` — consumed by Task 6's `main.py`.

- [ ] **Step 1: Write the failing test**

`host-app/tests/test_paired_devices.py`:

```python
from screentracker_host.paired_devices import PairedDevices


def test_approve_generates_a_token_and_marks_the_device_known(tmp_path):
    store = PairedDevices(tmp_path / "paired_devices.json")

    token = store.approve("dev-1", label="Test Phone")

    assert token
    assert store.is_known("dev-1")
    assert store.is_paired("dev-1", token)


def test_is_paired_rejects_a_wrong_token(tmp_path):
    store = PairedDevices(tmp_path / "paired_devices.json")
    store.approve("dev-1", label="Test Phone")

    assert not store.is_paired("dev-1", "wrong-token")


def test_unknown_device_is_neither_known_nor_paired(tmp_path):
    store = PairedDevices(tmp_path / "paired_devices.json")

    assert not store.is_known("dev-nope")
    assert not store.is_paired("dev-nope", "any-token")


def test_approvals_persist_across_a_fresh_instance_on_the_same_path(tmp_path):
    path = tmp_path / "paired_devices.json"
    first_store = PairedDevices(path)
    token = first_store.approve("dev-2", label="Test Tablet")

    second_store = PairedDevices(path)

    assert second_store.is_paired("dev-2", token)
```

- [ ] **Step 2: Run to verify RED**

Run (from `host-app/`): `./venv/Scripts/python.exe -m pytest tests/test_paired_devices.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement `paired_devices.py`**

```python
import json
import secrets
import time
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent.parent / "paired_devices.json"


class PairedDevices:
    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self._path = path
        self._devices: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            return json.loads(self._path.read_text())
        return {}

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._devices, indent=2))

    def is_known(self, device_id: str) -> bool:
        return device_id in self._devices

    def is_paired(self, device_id: str, token: str) -> bool:
        entry = self._devices.get(device_id)
        return entry is not None and entry["token"] == token

    def approve(self, device_id: str, label: str) -> str:
        token = secrets.token_urlsafe(24)
        self._devices[device_id] = {"token": token, "label": label, "paired_at": time.time()}
        self._save()
        return token
```

- [ ] **Step 4: Run to verify GREEN**

Run: `./venv/Scripts/python.exe -m pytest tests/test_paired_devices.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp/host-app
git add screentracker_host/paired_devices.py tests/test_paired_devices.py
git commit -m "feat: add persistent paired-device store"
```

---

### Task 5: Host app — async terminal approval prompt

**Files:**
- Create: `host-app/screentracker_host/pairing.py`
- Test: `host-app/tests/test_pairing.py`

**Interfaces:**
- Produces: `async request_approval(label: str, device_id: str, prompt_fn: Callable[[str], str] = input, timeout_seconds: float = APPROVAL_TIMEOUT_SECONDS) -> bool` — consumed by Task 6's `main.py`.

- [ ] **Step 1: Write the failing test**

`host-app/tests/test_pairing.py`:

```python
import pytest

from screentracker_host.pairing import request_approval


@pytest.mark.asyncio
async def test_returns_true_when_the_operator_types_y():
    approved = await request_approval("Test Phone", "dev-1", prompt_fn=lambda _: "y")
    assert approved is True


@pytest.mark.asyncio
async def test_is_case_and_whitespace_insensitive():
    approved = await request_approval("Test Phone", "dev-1", prompt_fn=lambda _: "  Y  ")
    assert approved is True


@pytest.mark.asyncio
async def test_returns_false_for_any_other_answer():
    approved = await request_approval("Test Phone", "dev-1", prompt_fn=lambda _: "n")
    assert approved is False


@pytest.mark.asyncio
async def test_returns_false_on_timeout():
    import time

    def slow_prompt(_: str) -> str:
        time.sleep(0.2)
        return "y"

    approved = await request_approval(
        "Test Phone", "dev-1", prompt_fn=slow_prompt, timeout_seconds=0.05
    )
    assert approved is False
```

- [ ] **Step 2: Run to verify RED**

Run (from `host-app/`): `./venv/Scripts/python.exe -m pytest tests/test_pairing.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement `pairing.py`**

```python
import asyncio
from collections.abc import Callable

APPROVAL_TIMEOUT_SECONDS = 60.0


async def request_approval(
    label: str,
    device_id: str,
    prompt_fn: Callable[[str], str] = input,
    timeout_seconds: float = APPROVAL_TIMEOUT_SECONDS,
) -> bool:
    """Ask a human at the terminal to approve a new device. Runs the
    (blocking) prompt in an executor so it never blocks the event loop.
    Returns False on timeout or any answer that isn't 'y'."""
    loop = asyncio.get_event_loop()
    prompt_text = f"New device requesting access: {label} ({device_id[:8]}) — approve? [y/N]: "
    try:
        answer = await asyncio.wait_for(
            loop.run_in_executor(None, prompt_fn, prompt_text),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        return False
    return answer.strip().lower() == "y"
```

- [ ] **Step 4: Run to verify GREEN**

Run: `./venv/Scripts/python.exe -m pytest tests/test_pairing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp/host-app
git add screentracker_host/pairing.py tests/test_pairing.py
git commit -m "feat: add async terminal device-approval prompt"
```

---

### Task 6: Host app — rewire main.py for registration, pairing, and authentication

**Files:**
- Modify: `host-app/screentracker_host/main.py`
- Test: `host-app/tests/test_main.py`

**Interfaces:**
- Consumes: `load_or_create_host_id` (Task 3), `PairedDevices` (Task 4), `request_approval` (Task 5), `SignalingClient` (existing), `HostPeerConnection` (existing).
- Produces: `_handle_peer_joined(...)` — a decomposed, independently testable function (unlike the rest of `main.py`'s orchestration).

- [ ] **Step 1: Write the failing test**

`host-app/tests/test_main.py`:

```python
from unittest.mock import AsyncMock

import pytest

from screentracker_host.main import _handle_peer_joined
from screentracker_host.paired_devices import PairedDevices


@pytest.mark.asyncio
async def test_known_device_with_valid_token_streams_without_a_prompt(tmp_path):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    token = paired_devices.approve("dev-1", label="Test Phone")
    client = AsyncMock()
    peer_connection = AsyncMock()
    peer_connection.create_offer.return_value.sdp = "v=0..."

    streaming = await _handle_peer_joined(
        {"device_id": "dev-1", "token": token},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is True
    client.send.assert_awaited_with({"type": "offer", "sdp": "v=0..."})


@pytest.mark.asyncio
async def test_invalid_token_is_rejected_and_releases_the_peer(tmp_path):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    client = AsyncMock()
    peer_connection = AsyncMock()

    streaming = await _handle_peer_joined(
        {"device_id": "dev-1", "token": "wrong-token"},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is False
    client.send.assert_any_await({"type": "authenticate-failed"})
    client.send.assert_any_await({"type": "release-peer"})
    peer_connection.create_offer.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_device_approved_by_operator_gets_paired_and_streams(tmp_path, monkeypatch):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    client = AsyncMock()
    peer_connection = AsyncMock()
    peer_connection.create_offer.return_value.sdp = "v=0..."
    monkeypatch.setattr(
        "screentracker_host.main.request_approval", AsyncMock(return_value=True)
    )

    streaming = await _handle_peer_joined(
        {"device_id": "dev-2", "token": None},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is True
    assert paired_devices.is_known("dev-2")
    sent_types = [call.args[0]["type"] for call in client.send.await_args_list]
    assert "pair-approved" in sent_types
    assert "offer" in sent_types


@pytest.mark.asyncio
async def test_unknown_device_rejected_by_operator_does_not_stream(tmp_path, monkeypatch):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    client = AsyncMock()
    peer_connection = AsyncMock()
    monkeypatch.setattr(
        "screentracker_host.main.request_approval", AsyncMock(return_value=False)
    )

    streaming = await _handle_peer_joined(
        {"device_id": "dev-3", "token": None},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is False
    assert not paired_devices.is_known("dev-3")
    client.send.assert_any_await({"type": "pair-rejected", "reason": "denied"})
    peer_connection.create_offer.assert_not_awaited()


@pytest.mark.asyncio
async def test_already_known_device_without_a_token_skips_the_prompt(tmp_path, monkeypatch):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    paired_devices.approve("dev-4", label="Already paired")
    client = AsyncMock()
    peer_connection = AsyncMock()
    peer_connection.create_offer.return_value.sdp = "v=0..."
    request_approval_mock = AsyncMock()
    monkeypatch.setattr("screentracker_host.main.request_approval", request_approval_mock)

    streaming = await _handle_peer_joined(
        {"device_id": "dev-4", "token": None},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is True
    request_approval_mock.assert_not_awaited()
```

- [ ] **Step 2: Run to verify RED**

Run (from `host-app/`): `./venv/Scripts/python.exe -m pytest tests/test_main.py -v`
Expected: FAIL — `_handle_peer_joined` doesn't exist

- [ ] **Step 3: Implement `main.py`**

Replace the full contents of `host-app/screentracker_host/main.py`:

```python
import asyncio
import os

from screentracker_host.host_identity import load_or_create_host_id
from screentracker_host.paired_devices import PairedDevices
from screentracker_host.pairing import request_approval
from screentracker_host.signaling_client import SignalingClient
from screentracker_host.webrtc_peer import HostPeerConnection


async def run() -> None:
    signaling_url = os.environ["SIGNALING_SERVER_URL"]
    client = SignalingClient(signaling_url)
    await client.connect()

    host_id = load_or_create_host_id()
    await client.send({"type": "register-host", "host_id": host_id})

    session_id = await client.create_session()
    print(f"Session ready. Share this code with your viewer: {session_id}")

    paired_devices = PairedDevices()
    peer_connection = HostPeerConnection()
    streaming = False

    try:
        async for message in client.messages():
            if message["type"] == "peer-joined":
                streaming = await _handle_peer_joined(
                    message,
                    client=client,
                    peer_connection=peer_connection,
                    paired_devices=paired_devices,
                    host_id=host_id,
                )
            elif message["type"] == "answer":
                await peer_connection.set_remote_answer(message["sdp"])
            elif message["type"] == "ice-candidate":
                await peer_connection.add_ice_candidate(message["candidate"])
            elif message["type"] == "peer-disconnected":
                if streaming:
                    print("Viewer disconnected.")
                    break
                print("A pending viewer disconnected before pairing completed.")
    finally:
        await peer_connection.close()
        await client.close()


async def _handle_peer_joined(
    message: dict,
    *,
    client: SignalingClient,
    peer_connection: HostPeerConnection,
    paired_devices: PairedDevices,
    host_id: str,
) -> bool:
    """Decide whether a joining viewer gets streamed to. Returns True once an
    offer has actually been sent (the caller uses this to know whether a
    later peer-disconnected means a real stream ended)."""
    device_id = message.get("device_id")
    token = message.get("token")

    if token is not None:
        if not device_id or not paired_devices.is_paired(device_id, token):
            await client.send({"type": "authenticate-failed"})
            await client.send({"type": "release-peer"})
            return False
    elif device_id and not paired_devices.is_known(device_id):
        approved = await request_approval(label="viewer device", device_id=device_id)
        if not approved:
            await client.send({"type": "pair-rejected", "reason": "denied"})
            await client.send({"type": "release-peer"})
            return False
        new_token = paired_devices.approve(device_id, label="viewer device")
        await client.send({"type": "pair-approved", "token": new_token, "host_id": host_id})

    offer = await peer_connection.create_offer()
    await client.send({"type": "offer", "sdp": offer.sdp})
    return True


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify GREEN**

Run: `./venv/Scripts/python.exe -m pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Run the full host-app suite**

Run: `./venv/Scripts/python.exe -m pytest -v`
Expected: all tests pass (no regressions in capture/signaling_client/webrtc_peer tests)

- [ ] **Step 6: Manual smoke test**

With the signaling server (Task 2's changes) running locally, run `python -m screentracker_host.main`. Confirm it prints `Session ready...` and does not crash. Full pairing-prompt verification happens in Task 10's end-to-end pass, once the viewer side (Tasks 7-8) exists.

- [ ] **Step 7: Commit**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp/host-app
git add screentracker_host/main.py tests/test_main.py
git commit -m "feat: wire host registration, pairing approval, and authentication into the CLI"
```

---

### Task 7: Viewer app — device identity and stored-pairing helpers

**Files:**
- Create: `viewer-app/src/deviceIdentity.ts`
- Test: `viewer-app/tests/deviceIdentity.test.ts`

**Interfaces:**
- Produces: `getOrCreateDeviceId(): string`, `getStoredPairing(): StoredPairing | null`, `storePairing(pairing: StoredPairing): void`, `clearStoredPairing(): void`, type `StoredPairing = { hostId: string; token: string }` — consumed by Task 8's `App.tsx`.

- [ ] **Step 1: Write the failing test**

`viewer-app/tests/deviceIdentity.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";
import {
  clearStoredPairing,
  getOrCreateDeviceId,
  getStoredPairing,
  storePairing,
} from "../src/deviceIdentity";

beforeEach(() => {
  localStorage.clear();
});

describe("getOrCreateDeviceId", () => {
  it("creates and persists a device id on first call", () => {
    const id = getOrCreateDeviceId();
    expect(id).toBeTruthy();
    expect(getOrCreateDeviceId()).toBe(id);
  });
});

describe("stored pairing", () => {
  it("returns null when nothing is stored", () => {
    expect(getStoredPairing()).toBeNull();
  });

  it("round-trips a stored pairing", () => {
    storePairing({ hostId: "host-1", token: "tok-1" });
    expect(getStoredPairing()).toEqual({ hostId: "host-1", token: "tok-1" });
  });

  it("clears a stored pairing", () => {
    storePairing({ hostId: "host-1", token: "tok-1" });
    clearStoredPairing();
    expect(getStoredPairing()).toBeNull();
  });

  it("treats corrupted stored JSON as no pairing", () => {
    localStorage.setItem("screentracker_pairing", "{not-json");
    expect(getStoredPairing()).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify RED**

Run (from `viewer-app/`): `npm test`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement `deviceIdentity.ts`**

```ts
const DEVICE_ID_KEY = "screentracker_device_id";
const PAIRING_KEY = "screentracker_pairing";

export interface StoredPairing {
  hostId: string;
  token: string;
}

export function getOrCreateDeviceId(): string {
  const existing = localStorage.getItem(DEVICE_ID_KEY);
  if (existing) return existing;
  const id = crypto.randomUUID();
  localStorage.setItem(DEVICE_ID_KEY, id);
  return id;
}

export function getStoredPairing(): StoredPairing | null {
  const raw = localStorage.getItem(PAIRING_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredPairing;
  } catch {
    return null;
  }
}

export function storePairing(pairing: StoredPairing): void {
  localStorage.setItem(PAIRING_KEY, JSON.stringify(pairing));
}

export function clearStoredPairing(): void {
  localStorage.removeItem(PAIRING_KEY);
}
```

- [ ] **Step 4: Run to verify GREEN**

Run: `npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp
git add viewer-app/src/deviceIdentity.ts viewer-app/tests/deviceIdentity.test.ts
git commit -m "feat: add viewer device identity and stored-pairing helpers"
```

---

### Task 8: Viewer app — wire pairing states into App.tsx

**Files:**
- Modify: `viewer-app/src/App.tsx`
- Test: `viewer-app/tests/App.test.tsx`

**Interfaces:**
- Consumes: `getOrCreateDeviceId`, `getStoredPairing`, `storePairing`, `clearStoredPairing` (Task 7).
- Produces: updated `App` root behavior — attempts silent auto-authentication before showing the join form; handles `pair-approved`, `pair-rejected`, `authenticate-failed`.

- [ ] **Step 1: Write the failing tests**

Add to `viewer-app/tests/App.test.tsx` (extend the existing `FakeWebSocket` class with `onopen`/`emitOpen`, matching the pattern already used in `useSignalingSocket.test.ts`):

```tsx
// Add to the existing FakeWebSocket class in this file:
//   onopen: (() => void) | null = null;
//   emitOpen() { this.onopen?.(); }

import { storePairing } from "../src/deviceIdentity";

// ... inside describe("App", () => { ... }):

it("auto-authenticates with a stored pairing instead of showing the join form", async () => {
  storePairing({ hostId: "host-1", token: "tok-1" });
  render(<App />);
  const socket = FakeWebSocket.instances[0];
  act(() => socket.emitOpen());

  expect(JSON.parse(socket.sent[0])).toMatchObject({
    type: "authenticate",
    host_id: "host-1",
    token: "tok-1",
  });
});

it("stores the pairing when pair-approved arrives", async () => {
  render(<App />);
  await joinWithCode("X7K2M9");
  const socket = FakeWebSocket.instances[0];

  act(() => socket.emitMessage({ type: "pair-approved", token: "tok-2", host_id: "host-2" }));

  expect(JSON.parse(localStorage.getItem("screentracker_pairing")!)).toEqual({
    hostId: "host-2",
    token: "tok-2",
  });
});

it("shows a human-readable error when pairing is rejected", async () => {
  render(<App />);
  await joinWithCode("X7K2M9");
  const socket = FakeWebSocket.instances[0];

  act(() => socket.emitMessage({ type: "pair-rejected", reason: "denied" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Access denied by host.");
});

it("clears the stored pairing and falls back to the join form on authenticate-failed", async () => {
  storePairing({ hostId: "host-1", token: "stale-token" });
  render(<App />);
  const socket = FakeWebSocket.instances[0];
  act(() => socket.emitOpen());

  act(() => socket.emitMessage({ type: "authenticate-failed" }));

  expect(await screen.findByLabelText("Digit 1 of 6")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify RED**

Run (from `viewer-app/`): `npm test`
Expected: FAIL — `App.tsx` doesn't send `authenticate`, doesn't handle the three new message types

- [ ] **Step 3: Implement the `App.tsx` changes**

Modify `viewer-app/src/App.tsx`. Add the import, add device-id/auto-auth state, extend the status type and the message-handling switch, and gate the join form on status:

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { SessionJoinForm } from "./components/SessionJoinForm";
import { VideoPlayer } from "./components/VideoPlayer";
import { useSignalingSocket } from "./hooks/useSignalingSocket";
import { useWebRTCViewer } from "./hooks/useWebRTCViewer";
import { clearStoredPairing, getOrCreateDeviceId, getStoredPairing, storePairing } from "./deviceIdentity";
import styles from "./App.module.css";

type ViewerStatus = "idle" | "authenticating" | "joining" | "streaming" | "error";

function sessionRejectedMessage(reason: string, retryAfterSeconds?: number): string {
  switch (reason) {
    case "expired":
      return "This session code has expired.";
    case "already-claimed":
      return "This session is already being viewed.";
    case "rate-limited": {
      const seconds = Math.ceil(retryAfterSeconds ?? 0);
      return `Too many attempts. Try again in ${seconds} second${seconds === 1 ? "" : "s"}.`;
    }
    default:
      return "Session code not found.";
  }
}

export function App() {
  const signalingServerUrl = import.meta.env.VITE_SIGNALING_SERVER_URL as string | undefined;

  if (!signalingServerUrl) {
    return (
      <div className={styles.shell}>
        <header className={styles.topBar}>
          <span className={styles.wordmark}>ScreenTracker</span>
        </header>
        <main className={styles.main}>
          <p className={styles.error} role="alert">
            Configuration error: VITE_SIGNALING_SERVER_URL is not set. Copy .env.example to
            .env in the repository root and restart the dev server.
          </p>
        </main>
      </div>
    );
  }

  return <Viewer signalingServerUrl={signalingServerUrl} />;
}

function Viewer({ signalingServerUrl }: { signalingServerUrl: string }) {
  const [status, setStatus] = useState<ViewerStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const { send, lastMessage, isConnected } = useSignalingSocket(signalingServerUrl);
  const deviceIdRef = useRef(getOrCreateDeviceId());
  const attemptedAutoAuthRef = useRef(false);

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
    if (!isConnected || attemptedAutoAuthRef.current) return;
    const pairing = getStoredPairing();
    if (!pairing) return;
    attemptedAutoAuthRef.current = true;
    setStatus("authenticating");
    send({
      type: "authenticate",
      host_id: pairing.hostId,
      device_id: deviceIdRef.current,
      token: pairing.token,
    });
  }, [isConnected, send]);

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
      case "pair-approved":
        storePairing({
          hostId: lastMessage.host_id as string,
          token: lastMessage.token as string,
        });
        break;
      case "pair-rejected":
        setStatus("error");
        setErrorMessage("Access denied by host.");
        break;
      case "authenticate-failed":
        clearStoredPairing();
        attemptedAutoAuthRef.current = false;
        setStatus("idle");
        break;
      case "session-expired":
        setStatus("error");
        setErrorMessage(
          sessionRejectedMessage(
            lastMessage.reason as string,
            lastMessage.retry_after_seconds as number | undefined
          )
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
    send({ type: "join-session", session_id: sessionId, device_id: deviceIdRef.current });
  }

  const showJoinForm = status === "idle" || status === "joining";

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
        {showJoinForm && <SessionJoinForm onJoin={handleJoin} />}
        {status === "authenticating" && <p className={styles.error}>Connecting with saved access…</p>}
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

- [ ] **Step 4: Run to verify GREEN**

Run: `npm test`
Expected: PASS (fix the placeholder test from Step 1 with a real assertion first, per that step's note)

- [ ] **Step 5: Run the full viewer-app suite and typecheck**

Run: `npm test && npm run build`
Expected: all tests pass, build succeeds with no type errors

- [ ] **Step 6: Commit**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp
git add viewer-app/src/App.tsx viewer-app/tests/App.test.tsx
git commit -m "feat: auto-authenticate paired devices and handle pairing states in the viewer"
```

---

### Task 9: Documentation — deployment guide and spec updates

**Files:**
- Create: `docs/deployment.md`
- Modify: `docs/api-spec.md`
- Modify: `docs/architecture.md`
- Modify: `README.md` (link to the new deployment doc)

**Interfaces:** None — documentation only.

- [ ] **Step 1: Create `docs/deployment.md`**

```md
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
   \`\`\`bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   \`\`\`
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
```

- [ ] **Step 2: Update `docs/api-spec.md`**

Add a new section after the existing "Join rate limiting" section:

```md
## Device pairing and authentication

| Message | Direction | Payload |
|---|---|---|
| `register-host` | Host → Server | `host_id: string` |
| `authenticate` | Viewer → Server | `host_id: string`, `device_id: string`, `token: string` |
| `pair-approved` | Host → Server → Viewer | `token: string`, `host_id: string` |
| `pair-rejected` | Host → Server → Viewer | `reason: string` |
| `authenticate-failed` | Host → Server → Viewer | — |
| `release-peer` | Host → Server | — |

`join-session` additionally carries an optional `device_id: string`. `peer-joined`
now carries `device_id: string | null` and `token: string | null` so the host can
tell a code-entry join (`token` absent) from a token-based `authenticate` join.

A device's first successful `join-session` triggers a one-time terminal approval
prompt on the host (60-second timeout). Approval issues a token via `pair-approved`,
which the viewer stores and uses via `authenticate` on every later connection —
no code entry needed again. Rejection or timeout sends `pair-rejected` and
`release-peer`, freeing the session slot for someone else. An `authenticate` with
an invalid or unknown token gets `authenticate-failed` and the same release.
```

- [ ] **Step 3: Update `docs/architecture.md`**

Add to the decisions log:

```md
- **Device pairing over a persistent `host_id`, not the ephemeral session code**: the session code stays short-lived (5-minute TTL, matches the plan's original UX rationale); a separate, disk-persisted `host_id` lets an already-approved device find its owner's current session without ever seeing a code. This keeps the two concerns — "is this a session worth joining right now" vs. "is this device allowed to join at all" — independent.
- **Pairing approval is a blocking terminal prompt, not a GUI**: matches the host app's existing CLI-only design (§ MVP design spec); a 60-second timeout keeps a pending request from hanging forever if the operator isn't watching.
```

- [ ] **Step 4: Update `README.md`**

Add a line to the Documentation section:

```md
- [Deployment](docs/deployment.md)
```

- [ ] **Step 5: Commit**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp
git add docs/deployment.md docs/api-spec.md docs/architecture.md README.md
git commit -m "docs: add deployment guide and document device pairing"
```

---

### Task 10: End-to-end verification and Definition of Done

**Files:** none created — this task verifies Tasks 1-9 together.

**Interfaces:** none — manual verification only.

- [ ] **Step 1: Run every automated test suite**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp/signaling-server && python -m pytest -v
cd ../host-app && ./venv/Scripts/python.exe -m pytest -v
cd ../viewer-app && npm test && npm run build
```

Expected: all PASS, build succeeds.

- [ ] **Step 2: Manual pairing flow — approve**

Run signaling server + host app + viewer app locally (same machine or same
network, per `README.md`). Join with the session code from a device whose
browser has never stored a pairing. Confirm the host's terminal shows the
approval prompt; type `y`. Confirm the stream starts and the browser's
`localStorage` now has a `screentracker_pairing` entry (check via devtools).

- [ ] **Step 3: Manual pairing flow — reject and re-join**

Restart the host app (fresh session code). From a *different*, never-paired
browser profile, join and reject (`n`) the prompt. Confirm the viewer shows
"Access denied by host." and does not stream. Confirm a *third* device can
still join the same session code afterward (the rejected slot was released).

- [ ] **Step 4: Manual pairing flow — reconnect without a code**

Restart the host app again (fresh session code, same `host_identity.json`
so `host_id` is unchanged). Reload the browser tab from Step 2 (the one
that got paired) — confirm it connects and streams automatically, without
ever showing the code-entry form.

- [ ] **Step 5: Manual pairing flow — timeout**

Trigger a pairing prompt and simply wait 60+ seconds without answering.
Confirm the host times out, sends the rejection, and the viewer shows the
rejected message.

- [ ] **Step 6: Tailscale deployment (if set up)**

If Tailscale is installed per `docs/deployment.md` by this point, repeat
Step 2 with the viewer device on a genuinely different network (e.g. phone
on mobile data) and confirm it still works. If Tailscale isn't set up yet,
note this as still-pending in `HANDOFF.md` rather than skipping silently.

- [ ] **Step 7: Definition of Done checklist** (standard §18)

- [ ] Code was actually run and observed working (Steps 2-6 above)
- [ ] Relevant tests written and passing (Step 1)
- [ ] `code-review` skill run over the branch
- [ ] Docs updated in the same PR (already done in Task 9)
- [ ] No schema/migration involved (no database)
- [ ] `HANDOFF.md` updated (Step 8)
- [ ] New config/secret files (`host_identity.json`, `paired_devices.json`) are gitignored, not committed
- [ ] Commit messages follow the standard, no AI co-author trailer

- [ ] **Step 8: Update `HANDOFF.md`**

Reflect the device pairing feature's completion, note whether Tailscale
end-to-end (Step 6) was actually exercised, and list the current last-3-commits.

- [ ] **Step 9: Commit**

```bash
cd C:/dev/ScreenTracker/.worktrees/feat-screen-view-mvp
git add HANDOFF.md
git commit -m "docs: update HANDOFF.md after device pairing and deployment work"
```
