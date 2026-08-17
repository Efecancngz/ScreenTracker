import logging
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.models import parse_inbound_message
from app.session_manager import (
    SessionAlreadyClaimedError,
    SessionExpiredError,
    SessionManager,
    SessionNotFoundError,
)

logger = logging.getLogger(__name__)

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
            elif message.type == "join-session":
                await _handle_join(connection_id, message.session_id, websocket)
            elif message.type in ("offer", "answer", "ice-candidate"):
                await _relay_to_peer(connection_id, raw)
    except WebSocketDisconnect:
        await _handle_disconnect(connection_id)
    except Exception:
        # Catch any other exception (e.g., JSON decode errors, transport exceptions)
        # to ensure cleanup always happens and peer is notified
        logger.exception("Connection %s failed; cleaning up", connection_id)
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
    except SessionAlreadyClaimedError:
        await websocket.send_json({"type": "session-expired", "reason": "already-claimed"})
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
