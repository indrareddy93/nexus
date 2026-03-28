"""Rate-limiting middleware — sliding window, per-IP."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from nexus.core.request import Request
from nexus.core.response import Response
from nexus.middleware.base import BaseMiddleware


class RateLimitMiddleware(BaseMiddleware):
    """
    Token-bucket / sliding-window rate limiter per client IP.

    Usage::

        app.add_middleware(
            RateLimitMiddleware,
            requests_per_window=100,
            window_seconds=60,
            burst=20,
        )
    """

    def __init__(
        self,
        call_next: Callable,
        *,
        requests_per_window: int = 60,
        window_seconds: float = 60.0,
        burst: int = 10,
        key_func: Callable | None = None,
        exempt_paths: list[str] | None = None,
    ) -> None:
        super().__init__(call_next)
        self.limit = requests_per_window
        self.window = window_seconds
        self.burst = burst
        self.key_func = key_func or self._default_key
        self.exempt_paths: set[str] = set(exempt_paths or ["/docs", "/redoc", "/openapi.json"])
        self._windows: dict[str, deque] = {}

    @staticmethod
    def _default_key(request: Request) -> str:
        client = request.client
        if client:
            return client[0]
        return request.headers.get("x-forwarded-for", "unknown").split(",")[0].strip()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.path in self.exempt_paths:
            return await call_next(request)

        key = self.key_func(request)
        now = time.monotonic()
        window_start = now - self.window

        bucket = self._windows.setdefault(key, deque())
        # Evict stale timestamps
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= self.limit + self.burst:
            retry_after = int(self.window - (now - bucket[0])) + 1
            return Response(
                "Too Many Requests",
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + retry_after)),
                    "Content-Type": "application/json",
                },
            )

        bucket.append(now)
        remaining = max(0, self.limit - len(bucket))
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(now + self.window))
        return response
