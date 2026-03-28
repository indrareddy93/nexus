"""
Nexus — ASGI core engine.

Uvicorn / Hypercorn compatible.
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable
from typing import Any

from nexus.core.openapi import OpenAPIEndpoints
from nexus.core.request import Request
from nexus.core.response import ErrorResponse, JSONResponse, Response
from nexus.core.routing import Route, Router
from nexus.di.dependencies import DIContainer


class Nexus(Router, OpenAPIEndpoints):
    """
    The main Nexus application class.

    Usage::

        from nexus import Nexus, Request, Response

        app = Nexus(title="My API", version="1.0.0")

        @app.get("/")
        async def index(request: Request) -> Response:
            return Response.json({"status": "ok"})

        # Run with uvicorn:
        # uvicorn myapp:app
    """

    def __init__(
        self,
        *,
        title: str = "Nexus API",
        version: str = "1.0.0",
        description: str = "",
        docs_url: str = "/docs",
        redoc_url: str = "/redoc",
        openapi_url: str = "/openapi.json",
        debug: bool = False,
        on_startup: list[Callable] | None = None,
        on_shutdown: list[Callable] | None = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.version = version
        self.description = description
        self.docs_url = docs_url
        self.redoc_url = redoc_url
        self.openapi_url = openapi_url
        self.debug = debug
        self.container = DIContainer()

        # Lifecycle hooks
        self._on_startup: list[Callable] = on_startup or []
        self._on_shutdown: list[Callable] = on_shutdown or []

        # Middleware stack (applied outermost-first)
        self._middleware_stack: list[Callable] = []

        # WebSocket rooms registry
        self._ws_rooms: dict[str, set] = {}

        self._docs_mounted = False
        self._handler_chain: Callable | None = None

    # ------------------------------------------------------------------
    # Middleware
    # ------------------------------------------------------------------

    def add_middleware(self, middleware_cls: type, **options: Any) -> None:
        """Register a middleware class (ASGI-style)."""
        self._middleware_stack.append((middleware_cls, options))
        self._handler_chain = None  # force rebuild

    def use(self, middleware_fn: Callable) -> None:
        """Register a raw async middleware function."""
        self._middleware_stack.append((None, middleware_fn))
        self._handler_chain = None  # force rebuild

    # ------------------------------------------------------------------
    # Sub-routers
    # ------------------------------------------------------------------

    def include_router(self, router: Router) -> None:
        """Mount all routes from *router* into this app."""
        for route in router.routes:
            full_path = self.prefix + route.path
            new_route = Route(
                path=full_path,
                methods=route.methods,
                handler=route.handler,
                name=route.name,
                tags=self.tags + route.tags,
                summary=route.summary,
                description=route.description,
                response_model=route.response_model,
                deprecated=route.deprecated,
                middlewares=self._middleware_stack_fns() + route.middlewares,
            )
            self.routes.append(new_route)

    def _middleware_stack_fns(self) -> list[Callable]:
        fns = []
        for item in self._middleware_stack:
            if item[0] is None:
                fns.append(item[1])
        return fns

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_startup(self, fn: Callable) -> Callable:
        self._on_startup.append(fn)
        return fn

    def on_shutdown(self, fn: Callable) -> Callable:
        self._on_shutdown.append(fn)
        return fn

    async def _run_startup(self) -> None:
        for fn in self._on_startup:
            if asyncio.iscoroutinefunction(fn):
                await fn()
            else:
                fn()

    async def _run_shutdown(self) -> None:
        for fn in self._on_shutdown:
            if asyncio.iscoroutinefunction(fn):
                await fn()
            else:
                fn()

    # ------------------------------------------------------------------
    # ASGI entry point
    # ------------------------------------------------------------------

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        scope_type = scope["type"]

        if scope_type == "lifespan":
            await self._handle_lifespan(scope, receive, send)

        elif scope_type == "http":
            # Mount docs on first real HTTP request (deferred so all routes are registered)
            if not self._docs_mounted:
                self._mount_openapi()
                self._docs_mounted = True
            await self._handle_http(scope, receive, send)

        elif scope_type == "websocket":
            await self._handle_websocket(scope, receive, send)

        else:
            pass  # Ignore unknown scope types

    async def _handle_lifespan(self, scope: dict, receive: Callable, send: Callable) -> None:
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                try:
                    await self._run_startup()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
                    return
            elif event["type"] == "lifespan.shutdown":
                try:
                    await self._run_shutdown()
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.shutdown.failed", "message": str(exc)})
                return

    async def _handle_http(self, scope: dict, receive: Callable, send: Callable) -> None:
        request = Request(scope, receive)

        # Build middleware chain once (lazy singleton)
        if self._handler_chain is None:
            self._handler_chain = self._build_handler_chain()
        response = await self._handler_chain(request)
        await response(scope, receive, send)

    async def _dispatch(self, request: Request) -> Response:
        """Core dispatch: match route → resolve deps → call handler."""
        match = self.match(request.path, request.method)
        if match is None:
            return ErrorResponse(
                f"Not found: {request.method} {request.path}",
                status_code=404,
                code="NOT_FOUND",
            )

        route, path_params = match
        request.path_params = path_params

        try:
            result = await self.container.resolve_handler(
                route.handler,
                path_params=path_params,
                request=request,
            )
        except Exception as exc:
            if self.debug:
                tb = traceback.format_exc()
                return ErrorResponse(str(exc), status_code=500, details=tb)
            return ErrorResponse("Internal server error", status_code=500)

        if isinstance(result, Response):
            return result
        if isinstance(result, dict):
            return JSONResponse(result)
        if isinstance(result, (str, bytes)):
            return Response(result, content_type="text/plain; charset=utf-8")
        # Last resort — wrap in JSON
        return JSONResponse(result)

    def _build_handler_chain(self) -> Callable:
        """Build the middleware + dispatch chain (called once, result is cached)."""

        async def final_handler(req: Request) -> Response:
            return await self._dispatch(req)

        handler: Callable = final_handler

        # Instantiate class-based middlewares once and chain them
        for item in reversed(self._middleware_stack):
            cls, opts_or_fn = item
            if cls is not None:
                # Class-based middleware — instantiate with call_next baked in
                handler = cls(handler, **opts_or_fn)
            else:
                # Function middleware: async def(request, call_next) -> Response
                prev = handler

                async def make_fn_handler(req: Request, *, _prev=prev, _fn=opts_or_fn) -> Response:
                    return await _fn(req, _prev)

                handler = make_fn_handler

        return handler

    async def _handle_websocket(self, scope: dict, receive: Callable, send: Callable) -> None:
        from nexus.websocket.connection import WebSocketConnection

        path = scope.get("path", "/")
        match = self.match(path, "WS")
        if match is None:
            await send({"type": "websocket.close", "code": 4004})
            return

        route, path_params = match
        conn = WebSocketConnection(scope, receive, send)
        conn.path_params = path_params

        try:
            await conn.accept()
            await route.handler(conn)
        except Exception:
            if self.debug:
                traceback.print_exc()
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # OpenAPI
    # ------------------------------------------------------------------

    def _mount_openapi(self) -> None:
        self.mount_docs(
            self.routes,
            title=self.title,
            version=self.version,
            description=self.description,
            docs_url=self.docs_url,
            redoc_url=self.redoc_url,
            openapi_url=self.openapi_url,
        )

    # ------------------------------------------------------------------
    # Service registration shortcut
    # ------------------------------------------------------------------

    def register(self, cls: type, factory: Callable | None = None) -> None:
        self.container.register(cls, factory)

    def register_instance(self, cls: type, instance: Any) -> None:
        self.container.register_instance(cls, instance)
