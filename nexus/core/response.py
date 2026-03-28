"""HTTP Response classes."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional


class Response:
    """
    Base HTTP response.

    Usage::

        return Response("Hello!", status_code=200, content_type="text/plain")
        return Response.json({"ok": True})
        return Response.html("<h1>Hi</h1>")
    """

    def __init__(
        self,
        body: str | bytes = "",
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        self.status_code = status_code
        self.headers: dict[str, str] = headers or {}
        self.content_type = content_type

        if isinstance(body, str):
            self._body = body.encode("utf-8")
        else:
            self._body = body

        self.headers.setdefault("content-type", self.content_type)
        self.headers["content-length"] = str(len(self._body))

    # ------------------------------------------------------------------
    # ASGI interface
    # ------------------------------------------------------------------

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": [
                    (k.lower().encode("latin-1"), v.encode("latin-1"))
                    for k, v in self.headers.items()
                ],
            }
        )
        await send({"type": "http.response.body", "body": self._body})

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def json(
        cls,
        data: Any,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        indent: int | None = None,
    ) -> "JSONResponse":
        return JSONResponse(data, status_code=status_code, headers=headers, indent=indent)

    @classmethod
    def html(
        cls,
        content: str,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> "HTMLResponse":
        return HTMLResponse(content, status_code=status_code, headers=headers)

    @classmethod
    def text(
        cls,
        content: str,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> "Response":
        return cls(content, status_code=status_code, headers=headers, content_type="text/plain; charset=utf-8")

    @classmethod
    def redirect(cls, url: str, *, status_code: int = 302) -> "Response":
        return cls("", status_code=status_code, headers={"location": url})

    @classmethod
    def no_content(cls) -> "Response":
        return cls("", status_code=204)

    def __repr__(self) -> str:
        return f"<Response {self.status_code}>"


class JSONResponse(Response):
    """Serialises *data* to JSON automatically."""

    def __init__(
        self,
        data: Any,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        indent: int | None = None,
    ) -> None:
        body = json.dumps(data, indent=indent, default=str)
        super().__init__(
            body,
            status_code=status_code,
            headers=headers,
            content_type="application/json",
        )
        self.data = data


class HTMLResponse(Response):
    """Serves HTML content."""

    def __init__(
        self,
        content: str,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            content,
            status_code=status_code,
            headers=headers,
            content_type="text/html; charset=utf-8",
        )


class StreamingResponse:
    """
    Streams an async generator as an HTTP response.

    Usage::

        async def generate():
            for i in range(10):
                yield f"data: {i}\\n\\n"
                await asyncio.sleep(0.1)

        return StreamingResponse(generate(), content_type="text/event-stream")
    """

    def __init__(
        self,
        generator: AsyncIterator[str | bytes],
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.generator = generator
        self.status_code = status_code
        self.headers = headers or {}
        self.content_type = content_type
        self.headers.setdefault("content-type", self.content_type)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": [
                    (k.lower().encode("latin-1"), v.encode("latin-1"))
                    for k, v in self.headers.items()
                ],
            }
        )
        async for chunk in self.generator:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b""})


class ErrorResponse(JSONResponse):
    """Standard error envelope."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str | None = None,
        details: Any = None,
    ) -> None:
        payload: dict[str, Any] = {"error": message}
        if code:
            payload["code"] = code
        if details is not None:
            payload["details"] = details
        super().__init__(payload, status_code=status_code)
