"""Dependency Injection — automatic resolution, scoped lifetimes, generator cleanup."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, TypeVar, get_type_hints

T = TypeVar("T")


class Depends:
    """
    Marker for dependency injection — works identically to FastAPI's Depends().

    Usage::

        async def get_db():
            db = Database()
            try:
                yield db
            finally:
                await db.close()

        async def get_current_user(token: str = Header(""), db=Depends(get_db)):
            return await db.find_user(token)

        @app.get("/profile")
        async def profile(user=Depends(get_current_user)):
            return Response.json(user)
    """

    __slots__ = ("dependency", "use_cache")

    def __init__(self, dependency: Callable, *, use_cache: bool = True) -> None:
        self.dependency = dependency
        self.use_cache = use_cache

    def __repr__(self) -> str:
        return f"Depends({self.dependency.__name__})"


class Injectable:
    """
    Base class for singleton-style injectable services.

    Register with the DI container and it will be auto-resolved::

        class DatabaseService(Injectable):
            def __init__(self, url: str = "sqlite:///app.db"):
                self.url = url

        app.register(DatabaseService)
    """
    pass


class DIContainer:
    """
    Async-capable dependency injection container.

    Supports:
    - Singleton services (registered by class)
    - Generator-based dependencies with cleanup
    - Recursive dependency resolution
    - Automatic path param / query param injection
    """

    def __init__(self) -> None:
        self._singletons: dict[type, Any] = {}
        self._factories: dict[type, Callable] = {}

    def register(self, cls: type[T], factory: Callable[..., T] | None = None) -> None:
        """Register a class (or factory function) as a resolvable service."""
        self._factories[cls] = factory or cls

    def register_instance(self, cls: type[T], instance: T) -> None:
        """Register an already-created instance as a singleton."""
        self._singletons[cls] = instance

    async def resolve(self, cls: type[T]) -> T:
        """Resolve a registered class to an instance."""
        if cls in self._singletons:
            return self._singletons[cls]
        factory = self._factories.get(cls)
        if factory is None:
            raise LookupError(f"No provider registered for {cls!r}. Call app.register({cls.__name__}) first.")
        if asyncio.iscoroutinefunction(factory):
            instance = await factory()
        else:
            instance = factory()
        self._singletons[cls] = instance
        return instance

    async def resolve_handler(
        self,
        handler: Callable,
        *,
        path_params: dict[str, str],
        request: Any,
    ) -> Any:
        """
        Call *handler* with all its dependencies resolved automatically.

        Resolution priority:
        1. ``request`` parameter → the Request object
        2. ``Depends(fn)`` defaults → resolved recursively
        3. Named path parameters (type-cast if annotated)
        4. Query parameters from the request
        5. Body fields (for POST/PUT/PATCH)
        6. Default values from the signature
        """
        sig = inspect.signature(handler)
        try:
            hints = get_type_hints(handler)
        except Exception:
            hints = {}

        kwargs: dict[str, Any] = {}
        cleanup_gens: list = []
        cache: dict[int, Any] = {}

        for name, param in sig.parameters.items():
            if name == "request":
                kwargs["request"] = request
                continue

            default = param.default

            if isinstance(default, Depends):
                value, gens = await self._resolve_depends(default, request=request, cache=cache)
                cleanup_gens.extend(gens)
                kwargs[name] = value
                continue

            if name in path_params:
                ann = hints.get(name, str)
                try:
                    kwargs[name] = ann(path_params[name])
                except (ValueError, TypeError):
                    kwargs[name] = path_params[name]
                continue

            if request is not None:
                qval = request.query(name)
                if qval is not None:
                    ann = hints.get(name, str)
                    try:
                        kwargs[name] = ann(qval)
                    except (ValueError, TypeError):
                        kwargs[name] = qval
                    continue

            if request is not None and getattr(request, "method", "") in ("POST", "PUT", "PATCH"):
                try:
                    body = await request.json()
                    if isinstance(body, dict) and name in body:
                        kwargs[name] = body[name]
                        continue
                except Exception:
                    pass

            if param.default is not inspect.Parameter.empty and not isinstance(param.default, Depends):
                kwargs[name] = param.default

        if asyncio.iscoroutinefunction(handler):
            result = await handler(**kwargs)
        else:
            result = handler(**kwargs)

        # Cleanup generator dependencies (run finally blocks)
        for gen in cleanup_gens:
            try:
                if inspect.isasyncgen(gen):
                    await gen.__anext__()
                else:
                    next(gen)
            except (StopAsyncIteration, StopIteration):
                pass
            except Exception:
                pass  # Suppress cleanup errors

        return result

    async def _resolve_depends(
        self,
        dep: Depends,
        *,
        request: Any,
        cache: dict[int, Any],
    ) -> tuple[Any, list]:
        """Resolve a Depends() marker recursively. Returns (value, generators_to_cleanup)."""
        key = id(dep.dependency)
        if dep.use_cache and key in cache:
            return cache[key], []

        fn = dep.dependency
        sig = inspect.signature(fn)
        sub_kwargs: dict[str, Any] = {}
        cleanup_gens: list = []

        for name, param in sig.parameters.items():
            if name == "request":
                sub_kwargs["request"] = request
            elif isinstance(param.default, Depends):
                val, gens = await self._resolve_depends(param.default, request=request, cache=cache)
                sub_kwargs[name] = val
                cleanup_gens.extend(gens)

        if asyncio.iscoroutinefunction(fn):
            value = await fn(**sub_kwargs)
        elif inspect.isasyncgenfunction(fn):
            gen = fn(**sub_kwargs)
            value = await gen.__anext__()
            cleanup_gens.append(gen)
        elif inspect.isgeneratorfunction(fn):
            gen = fn(**sub_kwargs)
            value = next(gen)
            cleanup_gens.append(gen)
        else:
            value = fn(**sub_kwargs)

        if dep.use_cache:
            cache[key] = value

        return value, cleanup_gens
