import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import websockets


class SignalingClient:
    def __init__(
        self,
        url: str,
        connect_timeout: float = 30.0,
        attempt_timeout: float = 2.0,
        retry_delay: float = 0.25,
    ) -> None:
        self._url = url
        self._connect_timeout = connect_timeout
        self._attempt_timeout = attempt_timeout
        self._retry_delay = retry_delay
        self._connection: websockets.WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        """Keep trying until the signaling server answers or the budget runs
        out. The host app is started next to the server (start-dev.bat, the
        tray launcher, a Windows-boot autostart), so the server is routinely
        still binding its port when the first attempt lands.

        Each attempt gets its own short timeout on purpose. websockets'
        10s default is fine against a port that refuses the connection, but
        SIGNALING_SERVER_URL usually points at a Tailscale address, where an
        unbound port silently *drops* packets instead of refusing them --
        one attempt then blocks for the full 10s and the unhandled error
        takes the whole host app down."""
        deadline = time.monotonic() + self._connect_timeout
        while True:
            try:
                self._connection = await websockets.connect(
                    self._url, open_timeout=self._attempt_timeout
                )
                return
            except (OSError, asyncio.TimeoutError):
                if time.monotonic() + self._retry_delay >= deadline:
                    raise
                await asyncio.sleep(self._retry_delay)

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
