"""Structured request/response logging middleware."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from nexus.core.request import Request
from nexus.core.response import Response
from nexus.middleware.base import BaseMiddleware

logger = logging.getLogger("nexus.access")


class LoggingMiddleware(BaseMiddleware):
    """
    Structured access log middleware.

    Logs: method, path, status, latency, and client IP.

    Usage::

        import logging
        logging.basicConfig(level=logging.INFO)

        app.add_middleware(LoggingMiddleware, log_level=logging.INFO)
    """

    def __init__(
        self,
        call_next: Callable,
        *,
        log_level: int = logging.INFO,
        log_body: bool = False,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(call_next)
        self.log_level = log_level
        self.log_body = log_body
        self.exclude_paths: set[str] = set(exclude_paths or ["/health", "/ping"])

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.path in self.exclude_paths:
            return await call_next(request)

        start = time.perf_counter()
        client_ip = ""
        if request.client:
            client_ip = request.client[0]

        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.log(
                self.log_level,
                '%s %s %s %.2fms [%s]',
                request.method,
                request.path,
                response.status_code,
                elapsed_ms,
                client_ip,
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "latency_ms": round(elapsed_ms, 2),
                    "client": client_ip,
                },
            )
            return response
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                'EXCEPTION %s %s %.2fms — %s',
                request.method,
                request.path,
                elapsed_ms,
                exc,
                exc_info=True,
            )
            raise
