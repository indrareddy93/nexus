"""CORS middleware — Cross-Origin Resource Sharing."""

from __future__ import annotations

from collections.abc import Callable

from nexus.core.request import Request
from nexus.core.response import Response
from nexus.middleware.base import BaseMiddleware


class CORSMiddleware(BaseMiddleware):
    """
    CORS middleware supporting simple and preflight requests.

    Usage::

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://example.com", "https://app.example.com"],
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=True,
            max_age=86400,
        )

    Set ``allow_origins=["*"]`` to allow all origins (not recommended in production).
    """

    def __init__(
        self,
        call_next: Callable,
        *,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        expose_headers: list[str] | None = None,
        allow_credentials: bool = False,
        max_age: int = 600,
    ) -> None:
        super().__init__(call_next)
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
        self.allow_headers = allow_headers or ["*"]
        self.expose_headers = expose_headers or []
        self.allow_credentials = allow_credentials
        self.max_age = max_age

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        origin = request.headers.get("origin", "")

        if request.method == "OPTIONS" and request.headers.get("access-control-request-method"):
            # Preflight
            return self._preflight_response(origin)

        response = await call_next(request)
        self._add_cors_headers(response, origin)
        return response

    def _is_allowed_origin(self, origin: str) -> bool:
        if "*" in self.allow_origins:
            return True
        return origin in self.allow_origins

    def _preflight_response(self, origin: str) -> Response:
        headers: dict[str, str] = {}
        if self._is_allowed_origin(origin):
            headers["Access-Control-Allow-Origin"] = origin if origin else "*"
        else:
            headers["Access-Control-Allow-Origin"] = ""

        headers["Access-Control-Allow-Methods"] = ", ".join(self.allow_methods)
        headers["Access-Control-Allow-Headers"] = (
            ", ".join(self.allow_headers) if self.allow_headers != ["*"] else "*"
        )
        headers["Access-Control-Max-Age"] = str(self.max_age)
        if self.allow_credentials:
            headers["Access-Control-Allow-Credentials"] = "true"

        return Response("", status_code=204, headers=headers)

    def _add_cors_headers(self, response: Response, origin: str) -> None:
        if self._is_allowed_origin(origin):
            response.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
        if self.expose_headers:
            response.headers["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)
        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"
