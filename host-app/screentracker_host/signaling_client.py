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
