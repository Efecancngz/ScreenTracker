import time
import asyncio
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


@pytest.mark.asyncio
async def test_connect_keeps_retrying_until_the_server_finishes_starting():
    """The host app is launched alongside the signaling server, so the
    server is regularly still importing and binding when the first connect
    attempt lands. One shot at it turns an ordinary startup race into a
    crash that takes the whole host app down.

    The server here appears later than a single websockets.connect() call
    survives on its own, so only real retrying can bridge the gap."""
    port = 8766

    async def serve_late():
        await asyncio.sleep(6.0)
        return await websockets.serve(_session_created_handler, "localhost", port)

    server_task = asyncio.create_task(serve_late())
    client = SignalingClient(
        f"ws://localhost:{port}", connect_timeout=20.0, attempt_timeout=0.3, retry_delay=0.1
    )

    await client.connect()
    session_id = await client.create_session()
    await client.close()

    server = await server_task
    server.close()
    await server.wait_closed()

    assert session_id == "test-session-id"


@pytest.mark.asyncio
async def test_connect_gives_up_once_the_timeout_budget_is_spent():
    """A server that never arrives must surface an error promptly instead
    of hanging. Against an address that silently drops packets rather than
    refusing them, an unbounded single attempt blocks for websockets'
    full 10s open_timeout -- which is what killed the host app."""
    client = SignalingClient(
        "ws://localhost:8767", connect_timeout=0.5, attempt_timeout=0.1, retry_delay=0.05
    )

    started = time.monotonic()
    with pytest.raises(OSError):
        await client.connect()
    elapsed = time.monotonic() - started

    assert elapsed < 3.0
