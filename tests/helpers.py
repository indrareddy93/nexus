"""Test helpers — lightweight ASGI test client."""

from __future__ import annotations

import asyncio
import json
from typing import Any


class MockReceive:
    """Simulates an ASGI receive channel with a pre-loaded body."""

    def __init__(self, body: bytes = b"") -> None:
        self._body = body
        self._sent = False

    async def __call__(self) -> dict:
        if not self._sent:
            self._sent = True
            return {"type": "http.request", "body": self._body, "more_body": False}
        # Block forever after body is consumed (simulates a live connection)
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}


class MockSend:
    """Captures ASGI send events into a simple response object."""

    def __init__(self) -> None:
        self.status: int = 200
        self.headers: dict[str, str] = {}
        self.body: bytes = b""

    async def __call__(self, event: dict) -> None:
        if event["type"] == "http.response.start":
            self.status = event["status"]
            self.headers = {
                k.decode("latin-1"): v.decode("latin-1")
                for k, v in event.get("headers", [])
            }
        elif event["type"] == "http.response.body":
            self.body += event.get("body", b"")

    def json(self) -> Any:
        return json.loads(self.body)

    def text(self) -> str:
        return self.body.decode("utf-8")


class TestClient:
    """Minimal synchronous test client for Nexus ASGI apps."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def _make_scope(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query_string: str = "",
    ) -> dict:
        raw_headers = [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in (headers or {}).items()
        ]
        return {
            "type": "http",
            "method": method.upper(),
            "path": path,
            "query_string": query_string.encode(),
            "headers": raw_headers,
            "client": ("127.0.0.1", 12345),
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | str | dict | None = None,
        headers: dict[str, str] | None = None,
        query_string: str = "",
    ) -> MockSend:
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            headers = {"content-type": "application/json", **(headers or {})}
        elif isinstance(body, str):
            body = body.encode()
        raw_body = body or b""

        scope = self._make_scope(method, path, headers=headers, query_string=query_string)
        receive = MockReceive(raw_body)
        send = MockSend()
        asyncio.get_event_loop().run_until_complete(self.app(scope, receive, send))
        return send

    def get(self, path: str, **kwargs: Any) -> MockSend:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> MockSend:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> MockSend:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> MockSend:
        return self.request("DELETE", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> MockSend:
        return self.request("PATCH", path, **kwargs)
