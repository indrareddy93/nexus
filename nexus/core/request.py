"""HTTP Request abstraction over ASGI scope/receive."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any


class Request:
    """
    Wraps an ASGI scope + receive callable into a convenient Request object.

    Attributes:
        method: HTTP method (GET, POST, …)
        path:   URL path (/api/users/1)
        headers: dict of lowercase header names → values
        path_params: dict populated by the router after matching
    """

    __slots__ = (
        "_scope",
        "_receive",
        "_body",
        "_json",
        "_query_params",
        "path_params",
        "state",
    )

    def __init__(self, scope: dict, receive: Any) -> None:
        self._scope = scope
        self._receive = receive
        self._body: bytes | None = None
        self._json: Any = _UNSET
        self._query_params: dict[str, str] | None = None
        self.path_params: dict[str, str] = {}
        self.state: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Basic properties
    # ------------------------------------------------------------------

    @property
    def method(self) -> str:
        return self._scope.get("method", "GET").upper()

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
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    @property
    def client(self) -> tuple[str, int] | None:
        return self._scope.get("client")

    # ------------------------------------------------------------------
    # Query params
    # ------------------------------------------------------------------

    @property
    def query_params(self) -> dict[str, str]:
        if self._query_params is None:
            self._query_params = dict(
                urllib.parse.parse_qsl(self.query_string, keep_blank_values=True)
            )
        return self._query_params

    def query(self, name: str, default: str | None = None) -> str | None:
        return self.query_params.get(name, default)

    # ------------------------------------------------------------------
    # Body
    # ------------------------------------------------------------------

    async def body(self) -> bytes:
        if self._body is None:
            chunks: list[bytes] = []
            while True:
                event = await self._receive()
                if event["type"] == "http.request":
                    chunks.append(event.get("body", b""))
                    if not event.get("more_body", False):
                        break
                elif event["type"] == "http.disconnect":
                    break
            self._body = b"".join(chunks)
        return self._body

    async def text(self, encoding: str = "utf-8") -> str:
        return (await self.body()).decode(encoding)

    async def json(self) -> Any:
        if self._json is _UNSET:
            raw = await self.body()
            try:
                self._json = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                self._json = None
        return self._json

    async def form(self) -> dict[str, str]:
        body = await self.text()
        return dict(urllib.parse.parse_qsl(body, keep_blank_values=True))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def header(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name.lower(), default)

    def __repr__(self) -> str:
        return f"<Request {self.method} {self.path}>"


_UNSET = object()
