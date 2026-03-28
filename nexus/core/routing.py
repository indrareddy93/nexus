"""Routing engine — path params, versioned APIs, middleware stacking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# Convert "/users/{id}/posts/{post_id}" → regex + param names
_PARAM_RE = re.compile(r"\{(\w+)(?::([^}]+))?\}")

_TYPE_CONVERTERS: dict[str, str] = {
    "int": r"[0-9]+",
    "str": r"[^/]+",
    "uuid": r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
    "path": r".+",
    "float": r"[0-9]*\.?[0-9]+",
}


def _compile_path(path: str) -> tuple[re.Pattern, list[str]]:
    """Return (compiled_regex, [param_names]) for a route path."""
    param_names: list[str] = []
    pattern = "^"
    last_end = 0
    for m in _PARAM_RE.finditer(path):
        pattern += re.escape(path[last_end : m.start()])
        name = m.group(1)
        type_hint = m.group(2) or "str"
        regex_part = _TYPE_CONVERTERS.get(type_hint, r"[^/]+")
        pattern += f"(?P<{name}>{regex_part})"
        param_names.append(name)
        last_end = m.end()
    pattern += re.escape(path[last_end:]) + "$"
    return re.compile(pattern), param_names


@dataclass
class Route:
    """A single route definition."""

    path: str
    methods: set[str]
    handler: Callable
    name: str | None = None
    tags: list[str] = field(default_factory=list)
    summary: str | None = None
    description: str | None = None
    response_model: type | None = None
    deprecated: bool = False
    middlewares: list[Callable] = field(default_factory=list)

    # compiled at registration time
    _regex: re.Pattern = field(init=False, repr=False)
    _param_names: list[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._regex, self._param_names = _compile_path(self.path)

    def match(self, path: str) -> dict[str, str] | None:
        """Return path params dict if *path* matches, else None."""
        m = self._regex.match(path)
        if m is None:
            return None
        return m.groupdict()


class Router:
    """
    Collects routes and sub-routers.

    Usage::

        router = Router(prefix="/api/v1", tags=["v1"])

        @router.get("/users")
        async def list_users(request): ...

        app.include_router(router)
    """

    def __init__(
        self,
        prefix: str = "",
        tags: list[str] | None = None,
        middlewares: list[Callable] | None = None,
    ) -> None:
        self.prefix = prefix.rstrip("/")
        self.tags: list[str] = tags or []
        self.middlewares: list[Callable] = middlewares or []
        self.routes: list[Route] = []

    # ------------------------------------------------------------------
    # Decorator API
    # ------------------------------------------------------------------

    def route(
        self,
        path: str,
        methods: list[str],
        *,
        name: str | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        description: str | None = None,
        response_model: type | None = None,
        deprecated: bool = False,
        middlewares: list[Callable] | None = None,
    ) -> Callable:
        def decorator(fn: Callable) -> Callable:
            full_path = self.prefix + path
            r = Route(
                path=full_path,
                methods={m.upper() for m in methods},
                handler=fn,
                name=name or fn.__name__,
                tags=(tags or []) + self.tags,
                summary=summary or fn.__doc__,
                description=description,
                response_model=response_model,
                deprecated=deprecated,
                middlewares=middlewares or [],
            )
            self.routes.append(r)
            return fn
        return decorator

    def get(self, path: str, **kwargs: Any) -> Callable:
        return self.route(path, ["GET"], **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable:
        return self.route(path, ["POST"], **kwargs)

    def put(self, path: str, **kwargs: Any) -> Callable:
        return self.route(path, ["PUT"], **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Callable:
        return self.route(path, ["PATCH"], **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Callable:
        return self.route(path, ["DELETE"], **kwargs)

    def head(self, path: str, **kwargs: Any) -> Callable:
        return self.route(path, ["HEAD"], **kwargs)

    def options(self, path: str, **kwargs: Any) -> Callable:
        return self.route(path, ["OPTIONS"], **kwargs)

    def ws(self, path: str, **kwargs: Any) -> Callable:
        """Register a WebSocket route."""
        return self.route(path, ["WS"], **kwargs)

    # ------------------------------------------------------------------
    # Sub-router mounting
    # ------------------------------------------------------------------

    def include_router(self, router: "Router") -> None:
        for route in router.routes:
            new_route = Route(
                path=self.prefix + route.path,
                methods=route.methods,
                handler=route.handler,
                name=route.name,
                tags=self.tags + route.tags,
                summary=route.summary,
                description=route.description,
                response_model=route.response_model,
                deprecated=route.deprecated,
                middlewares=self.middlewares + route.middlewares,
            )
            self.routes.append(new_route)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def match(self, path: str, method: str) -> tuple[Route, dict[str, str]] | None:
        """Find a matching route and extract path params."""
        method = method.upper()
        for route in self.routes:
            params = route.match(path)
            if params is not None:
                if method in route.methods or "WS" in route.methods:
                    return route, params
                # Method not allowed — keep looking for the same path
        return None


def include_router(app: Any, router: Router) -> None:
    """Convenience function to include a router into an app."""
    app.include_router(router)
