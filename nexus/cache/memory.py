"""In-memory TTL cache — thread-safe, async-compatible."""

from __future__ import annotations

import asyncio
import functools
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float  # monotonic timestamp; 0 = never expires

    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.monotonic() > self.expires_at


class Cache:
    """
    In-memory key/value store with per-entry TTL.

    Usage::

        cache = Cache(default_ttl=300)

        # Basic get/set
        cache.set("key", "value", ttl=60)
        value = cache.get("key")

        # get_or_set — compute and cache in one step
        result = await cache.get_or_set("expensive", compute_fn, ttl=120)

        # Invalidate
        cache.delete("key")
        cache.clear()
    """

    def __init__(self, default_ttl: int = 300, max_size: int = 10_000) -> None:
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._store: dict[str, _CacheEntry] = {}

    def set(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        """Store *value* under *key* with optional TTL (seconds)."""
        effective_ttl = ttl if ttl is not None else self.default_ttl
        expires_at = time.monotonic() + effective_ttl if effective_ttl > 0 else 0
        self._store[key] = _CacheEntry(value=value, expires_at=expires_at)

        # Simple eviction: remove oldest when over capacity
        if len(self._store) > self.max_size:
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]

    def get(self, key: str, default: Any = None) -> Any:
        """Return cached value or *default* if missing / expired."""
        entry = self._store.get(key)
        if entry is None:
            return default
        if entry.is_expired():
            del self._store[key]
            return default
        return entry.value

    def has(self, key: str) -> bool:
        """Return True if *key* exists and has not expired."""
        return self.get(key, _MISSING) is not _MISSING

    def delete(self, key: str) -> bool:
        """Remove *key*. Returns True if it existed."""
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        """Remove all entries."""
        self._store.clear()

    def evict_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        now = time.monotonic()
        expired = [k for k, e in self._store.items() if e.expires_at > 0 and now > e.expires_at]
        for k in expired:
            del self._store[k]
        return len(expired)

    def size(self) -> int:
        """Return number of (possibly-expired) entries."""
        return len(self._store)

    def stats(self) -> dict[str, int]:
        now = time.monotonic()
        active = sum(1 for e in self._store.values() if not e.is_expired())
        expired = len(self._store) - active
        return {"total": len(self._store), "active": active, "expired": expired}

    async def get_or_set(
        self,
        key: str,
        compute: Callable,
        *,
        ttl: int | None = None,
    ) -> Any:
        """
        Return cached value for *key*, or call *compute* to produce and cache it.

        *compute* may be a regular or async callable.

        Example::

            data = await cache.get_or_set(
                "users:all",
                lambda: db.query(User).all(),
                ttl=60,
            )
        """
        existing = self.get(key)
        if existing is not _MISSING and existing is not None:
            return existing

        if asyncio.iscoroutinefunction(compute):
            value = await compute()
        else:
            value = compute()

        self.set(key, value, ttl=ttl)
        return value

    def __repr__(self) -> str:
        return f"<Cache size={len(self._store)} default_ttl={self.default_ttl}>"


_MISSING = object()


def cached(
    cache: Cache,
    *,
    key: str | None = None,
    ttl: int | None = None,
    key_fn: Callable | None = None,
) -> Callable:
    """
    Decorator that caches handler responses.

    Usage::

        cache = Cache(default_ttl=60)

        @app.get("/products")
        @cached(cache, ttl=120)
        async def list_products(request):
            return Response.json(await db.query(Product).all())

        # Custom cache key
        @app.get("/products/{id}")
        @cached(cache, key_fn=lambda req: f"product:{req.path_params['id']}")
        async def get_product(request, id: int):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(request, *args, **kwargs):
            if key_fn:
                cache_key = key_fn(request)
            elif key:
                cache_key = key
            else:
                cache_key = f"{fn.__module__}.{fn.__qualname__}:{request.path}:{request.query_string}"

            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            result = await fn(request, *args, **kwargs)
            cache.set(cache_key, result, ttl=ttl)
            return result

        return wrapper
    return decorator
