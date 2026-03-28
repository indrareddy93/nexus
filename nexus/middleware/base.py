"""Base middleware class and function-middleware helper."""

from __future__ import annotations

from typing import Any, Callable

from nexus.core.request import Request
from nexus.core.response import Response


class BaseMiddleware:
    """
    Base class for Nexus middleware.

    Subclass and override ``dispatch`` to add behaviour before/after handlers.

    Usage::

        class TimingMiddleware(BaseMiddleware):
            async def dispatch(self, request: Request, call_next) -> Response:
                import time
                start = time.perf_counter()
                response = await call_next(request)
                elapsed = time.perf_counter() - start
                response.headers["X-Process-Time"] = f"{elapsed:.4f}s"
                return response

        app.add_middleware(TimingMiddleware)
    """

    def __init__(self, call_next: Callable) -> None:
        self.call_next = call_next

    async def __call__(self, request: Request) -> Response:
        return await self.dispatch(request, self.call_next)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        return await call_next(request)


def middleware(fn: Callable) -> Callable:
    """
    Decorator to create a function-style middleware.

    Usage::

        @middleware
        async def my_middleware(request, call_next):
            print(f"Before: {request.path}")
            response = await call_next(request)
            print(f"After: {response.status_code}")
            return response
    """
    return fn
