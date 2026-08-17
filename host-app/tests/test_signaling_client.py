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
