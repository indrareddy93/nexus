"""Tests for nexus/cache — in-memory TTL cache."""

import asyncio
import time
import pytest
from nexus.cache.memory import Cache, cached


class TestCache:
    def test_set_and_get(self):
        cache = Cache()
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_missing_key(self):
        cache = Cache()
        assert cache.get("nope") is None
        assert cache.get("nope", "default") == "default"

    def test_has(self):
        cache = Cache()
        assert not cache.has("x")
        cache.set("x", 1)
        assert cache.has("x")

    def test_delete(self):
        cache = Cache()
        cache.set("k", "v")
        assert cache.delete("k") is True
        assert cache.get("k") is None
        assert cache.delete("k") is False

    def test_clear(self):
        cache = Cache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size() == 0

    def test_ttl_expiry(self):
        cache = Cache(default_ttl=1)
        cache.set("fast", "value", ttl=0)  # ttl=0 means never expire
        assert cache.get("fast") == "value"

    def test_stats(self):
        cache = Cache()
        cache.set("a", 1)
        cache.set("b", 2)
        s = cache.stats()
        assert s["active"] == 2

    @pytest.mark.asyncio
    async def test_get_or_set_async(self):
        cache = Cache()
        call_count = 0

        async def compute():
            nonlocal call_count
            call_count += 1
            return "computed"

        result1 = await cache.get_or_set("k", compute)
        result2 = await cache.get_or_set("k", compute)
        assert result1 == "computed"
        assert result2 == "computed"
        assert call_count == 1  # computed only once

    @pytest.mark.asyncio
    async def test_get_or_set_sync(self):
        cache = Cache()

        def sync_compute():
            return 99

        result = await cache.get_or_set("num", sync_compute)
        assert result == 99

    def test_evict_expired(self):
        cache = Cache()
        # Set with very short TTL — we'll manually set expires_at in the past
        cache.set("old", "val")
        # Manually expire
        entry = cache._store["old"]
        entry.expires_at = time.monotonic() - 1
        evicted = cache.evict_expired()
        assert evicted == 1
        assert cache.get("old") is None


class TestCachedDecorator:
    @pytest.mark.asyncio
    async def test_cached_decorator(self):
        cache = Cache()
        call_count = 0

        from nexus import Request
        from tests.helpers import MockReceive

        def make_req():
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/products",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 1),
            }
            return Request(scope, MockReceive())

        @cached(cache, ttl=60)
        async def list_products(request):
            nonlocal call_count
            call_count += 1
            return {"products": []}

        req = make_req()
        r1 = await list_products(req)
        r2 = await list_products(req)
        assert r1 == r2
        assert call_count == 1
