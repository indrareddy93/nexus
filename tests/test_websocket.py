"""Tests for nexus/websocket — connection wrapper and room manager."""

import asyncio
import json
import pytest
from nexus.websocket.connection import RoomManager, WebSocketConnection, WebSocketRoom


def make_ws_connection(messages=None):
    """Create a mock WebSocket connection."""
    scope = {
        "type": "websocket",
        "path": "/ws",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
    }

    msg_queue = list(messages or [])
    sent = []

    async def receive():
        if msg_queue:
            text = msg_queue.pop(0)
            return {"type": "websocket.receive", "text": text}
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(event):
        sent.append(event)

    ws = WebSocketConnection(scope, receive, send)
    return ws, sent


class TestWebSocketConnection:
    @pytest.mark.asyncio
    async def test_accept(self):
        ws, sent = make_ws_connection()
        await ws.accept()
        assert sent[0]["type"] == "websocket.accept"

    @pytest.mark.asyncio
    async def test_send_text(self):
        ws, sent = make_ws_connection()
        await ws.send_text("hello")
        assert any(e.get("text") == "hello" for e in sent)

    @pytest.mark.asyncio
    async def test_send_json(self):
        ws, sent = make_ws_connection()
        await ws.send_json({"event": "msg", "data": "test"})
        last = sent[-1]
        parsed = json.loads(last["text"])
        assert parsed["event"] == "msg"

    @pytest.mark.asyncio
    async def test_receive_text(self):
        ws, _ = make_ws_connection(["Hello World"])
        msg = await ws.receive_text()
        assert msg == "Hello World"

    @pytest.mark.asyncio
    async def test_receive_disconnect(self):
        ws, _ = make_ws_connection([])
        msg = await ws.receive_text()
        assert msg is None

    @pytest.mark.asyncio
    async def test_async_iteration(self):
        ws, _ = make_ws_connection(["msg1", "msg2"])
        received = []
        async for msg in ws:
            received.append(msg)
        assert received == ["msg1", "msg2"]

    @pytest.mark.asyncio
    async def test_close(self):
        ws, sent = make_ws_connection()
        await ws.close(code=1001)
        assert any(e["type"] == "websocket.close" for e in sent)


class TestWebSocketRoom:
    @pytest.mark.asyncio
    async def test_add_and_broadcast(self):
        room = WebSocketRoom("test-room")
        ws1, sent1 = make_ws_connection()
        ws2, sent2 = make_ws_connection()

        room.add(ws1)
        room.add(ws2)
        assert room.size == 2

        n = await room.broadcast_text("hello")
        assert n == 2
        assert any(e.get("text") == "hello" for e in sent1)
        assert any(e.get("text") == "hello" for e in sent2)

    @pytest.mark.asyncio
    async def test_remove(self):
        room = WebSocketRoom("r")
        ws, _ = make_ws_connection()
        room.add(ws)
        room.remove(ws)
        assert room.size == 0

    @pytest.mark.asyncio
    async def test_broadcast_json(self):
        room = WebSocketRoom("json-room")
        ws, sent = make_ws_connection()
        room.add(ws)
        await room.broadcast_json({"action": "update"})
        data = json.loads(sent[-1]["text"])
        assert data["action"] == "update"


class TestRoomManager:
    def test_get_or_create(self):
        mgr = RoomManager()
        room1 = mgr.get_or_create("lobby")
        room2 = mgr.get_or_create("lobby")
        assert room1 is room2

    def test_delete(self):
        mgr = RoomManager()
        mgr.get_or_create("temp")
        mgr.delete("temp")
        assert mgr.get("temp") is None

    @pytest.mark.asyncio
    async def test_stats(self):
        mgr = RoomManager()
        room = mgr.get_or_create("room1")
        ws, _ = make_ws_connection()
        room.add(ws)
        s = mgr.stats()
        assert s["rooms"] == 1
        assert s["total_connections"] == 1
