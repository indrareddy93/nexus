"""WebSocket connection wrapper and pub/sub room manager."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Callable, Optional


class WebSocketConnection:
    """
    Wraps an ASGI WebSocket scope/receive/send into a convenient API.

    Usage::

        @app.ws("/chat/{room}")
        async def chat(ws: WebSocketConnection):
            await ws.accept()
            async for message in ws:
                await ws.send_json({"echo": message})
    """

    def __init__(self, scope: dict, receive: Callable, send: Callable) -> None:
        self._scope = scope
        self._receive = receive
        self._send = send
        self.path_params: dict[str, str] = {}
        self.state: dict[str, Any] = {}
        self._closed = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def path(self) -> str:
        return self._scope.get("path", "/")

    @property
    def headers(self) -> dict[str, str]:
        raw = self._scope.get("headers", [])
        return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw}

    @property
    def query_string(self) -> str:
        qs = self._scope.get("query_string", b"")
        return qs.decode("latin-1") if isinstance(qs, bytes) else qs

    @property
    def client(self) -> tuple[str, int] | None:
        return self._scope.get("client")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def accept(self, subprotocol: str | None = None) -> None:
        """Complete the WebSocket handshake."""
        msg: dict[str, Any] = {"type": "websocket.accept"}
        if subprotocol:
            msg["subprotocol"] = subprotocol
        await self._send(msg)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Send a close frame."""
        if not self._closed:
            self._closed = True
            await self._send({"type": "websocket.close", "code": code, "reason": reason})

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    async def receive_raw(self) -> bytes | str | None:
        """Receive the next message (text or bytes). Returns None on close."""
        event = await self._receive()
        if event["type"] == "websocket.receive":
            return event.get("text") or event.get("bytes")
        if event["type"] == "websocket.disconnect":
            self._closed = True
            return None
        return None

    async def receive_text(self) -> str | None:
        """Receive next message as text."""
        raw = await self.receive_raw()
        if raw is None:
            return None
        return raw if isinstance(raw, str) else raw.decode("utf-8")

    async def receive_json(self) -> Any:
        """Receive next message and parse as JSON."""
        text = await self.receive_text()
        if text is None:
            return None
        return json.loads(text)

    async def receive_bytes(self) -> bytes | None:
        """Receive next message as raw bytes."""
        raw = await self.receive_raw()
        if raw is None:
            return None
        return raw if isinstance(raw, bytes) else raw.encode("utf-8")

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_text(self, data: str) -> None:
        await self._send({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        await self._send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any, *, default: Callable | None = None) -> None:
        await self.send_text(json.dumps(data, default=default or str))

    # ------------------------------------------------------------------
    # Async iteration
    # ------------------------------------------------------------------

    def __aiter__(self) -> "WebSocketConnection":
        return self

    async def __anext__(self) -> str:
        msg = await self.receive_text()
        if msg is None:
            raise StopAsyncIteration
        return msg


class WebSocketRoom:
    """
    A named pub/sub room that broadcasts to multiple connected clients.

    Usage::

        room = WebSocketRoom("chat-room-1")
        room.add(ws)
        await room.broadcast_json({"event": "message", "data": "Hello!"})
        room.remove(ws)
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._connections: set[WebSocketConnection] = set()
        self._lock = asyncio.Lock()

    def add(self, ws: WebSocketConnection) -> None:
        self._connections.add(ws)

    def remove(self, ws: WebSocketConnection) -> None:
        self._connections.discard(ws)

    @property
    def size(self) -> int:
        return len(self._connections)

    async def broadcast_text(self, message: str) -> int:
        """Broadcast text to all connections. Returns number of successful sends."""
        sent = 0
        dead: list[WebSocketConnection] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)
        return sent

    async def broadcast_json(self, data: Any) -> int:
        return await self.broadcast_text(json.dumps(data, default=str))

    async def broadcast_bytes(self, data: bytes) -> int:
        sent = 0
        dead: list[WebSocketConnection] = []
        for ws in list(self._connections):
            try:
                await ws.send_bytes(data)
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)
        return sent

    def __repr__(self) -> str:
        return f"<WebSocketRoom {self.name!r} connections={self.size}>"


class RoomManager:
    """
    Manages multiple named WebSocket rooms.

    Usage::

        rooms = RoomManager()

        @app.ws("/chat/{room_id}")
        async def chat(ws: WebSocketConnection):
            room_id = ws.path_params["room_id"]
            room = rooms.get_or_create(room_id)
            room.add(ws)
            try:
                async for message in ws:
                    data = json.loads(message)
                    await room.broadcast_json({"from": "user", "text": data["text"]})
            finally:
                room.remove(ws)
                if room.size == 0:
                    rooms.delete(room_id)
    """

    def __init__(self) -> None:
        self._rooms: dict[str, WebSocketRoom] = {}

    def get_or_create(self, name: str) -> WebSocketRoom:
        if name not in self._rooms:
            self._rooms[name] = WebSocketRoom(name)
        return self._rooms[name]

    def get(self, name: str) -> Optional[WebSocketRoom]:
        return self._rooms.get(name)

    def delete(self, name: str) -> None:
        self._rooms.pop(name, None)

    def all_rooms(self) -> list[WebSocketRoom]:
        return list(self._rooms.values())

    def stats(self) -> dict[str, Any]:
        return {
            "rooms": len(self._rooms),
            "total_connections": sum(r.size for r in self._rooms.values()),
            "room_details": {name: r.size for name, r in self._rooms.items()},
        }
