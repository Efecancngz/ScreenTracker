import logging
import secrets
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.staticfiles import StaticFiles

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
# host_id -> the secret its first registrant proved ownership with. Without
# this, register-host had no ownership check at all: any connection could
# claim any host_id (learned by any viewer that ever paired with it, via
# pair-approved) and hijack it, capturing a later victim's auth token via
# the peer-joined relay. Never evicted -- a host_id is a long-lived,
# persisted identity (host_identity.json), not a per-connection value.
_host_secrets: dict[str, str] = {}

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
                _handle_register_host(connection_id, message.host_id, message.host_secret)
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

    # A hammered lock counts as a failure too (and re-locks with a longer
    # backoff), so a client that ignores the wait time escalates toward
    # being kicked instead of being allowed to poll the lock for free.
    if rate_limiter.seconds_until_unlocked(client_key) > 0:
        await _handle_join_failure(websocket, client_key, "rate-limited")
        return

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


def _handle_register_host(connection_id: str, host_id: str, host_secret: str) -> None:
    known_secret = _host_secrets.get(host_id)
    if known_secret is None:
        # First time this host_id has ever been registered -- trust on
        # first use, the only option with no central authority. From here
        # on, only a connection presenting this same secret may claim it.
        _host_secrets[host_id] = host_secret
    elif not secrets.compare_digest(known_secret, host_secret):
        logger.warning("Rejected register-host for %r: secret mismatch", host_id)
        return
    _host_ids[host_id] = connection_id


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
    session = None
    session_id = _connection_sessions.pop(connection_id, None)
    if session_id is not None:
        session = session_manager.get_session(session_id)
    _connections.pop(connection_id, None)
    for host_id, mapped_connection_id in list(_host_ids.items()):
        if mapped_connection_id == connection_id:
            del _host_ids[host_id]

    if peer_ws is not None:
        await peer_ws.send_json({"type": "peer-disconnected"})
    if session_id is not None:
        if session is not None and session.host_connection_id != connection_id:
            # The viewer disconnected, not the host (e.g. a page refresh) —
            # only free the viewer slot so the session survives and a
            # reconnect (via stored pairing or the same code) can re-claim
            # it without the host needing to restart.
            session_manager.release_viewer(session_id)
        else:
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


# The built viewer app (`npm run build` in viewer-app/, output dir `dist`) is
# served from the same origin as this server so a phone only ever needs one
# URL. Mounted last — and after the "/ws" route above — so it only ever
# catches plain HTTP requests that nothing else matched; a Mount registered
# before the websocket route would intercept "/ws" connections too, since
# Starlette tries routes in registration order.
_VIEWER_DIST = Path(__file__).resolve().parent.parent.parent / "viewer-app" / "dist"
if _VIEWER_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_VIEWER_DIST, html=True), name="viewer")
else:
    logger.warning(
        "Viewer build not found at %s — run `npm run build` in viewer-app/ to serve it "
        "from here. The signaling API still works without it.",
        _VIEWER_DIST,
    )
