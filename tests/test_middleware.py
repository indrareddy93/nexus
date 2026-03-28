"""Tests for nexus/middleware — CORS, rate limiting, logging."""

import pytest
from nexus import Nexus, Request, Response
from nexus.middleware import CORSMiddleware, RateLimitMiddleware, LoggingMiddleware
from tests.helpers import TestClient


class TestCORSMiddleware:
    def _make_app(self, **cors_opts):
        app = Nexus()
        app.add_middleware(CORSMiddleware, **cors_opts)

        @app.get("/data")
        async def data(request):
            return Response.json({"ok": True})

        return app

    def test_cors_header_added(self):
        app = self._make_app(allow_origins=["https://example.com"])
        client = TestClient(app)
        resp = client.get("/data", headers={"origin": "https://example.com"})
        assert "access-control-allow-origin" in resp.headers

    def test_wildcard_origin(self):
        app = self._make_app(allow_origins=["*"])
        client = TestClient(app)
        resp = client.get("/data", headers={"origin": "https://anything.com"})
        assert resp.headers.get("access-control-allow-origin") in ("https://anything.com", "*")


class TestRateLimitMiddleware:
    def test_headers_added(self):
        app = Nexus()
        app.add_middleware(RateLimitMiddleware, requests_per_window=100, window_seconds=60)

        @app.get("/api")
        async def api(request):
            return Response.json({"ok": True})

        client = TestClient(app)
        resp = client.get("/api")
        assert resp.status == 200
        assert "x-ratelimit-limit" in resp.headers

    def test_rate_limit_exceeded(self):
        app = Nexus()
        app.add_middleware(RateLimitMiddleware, requests_per_window=2, window_seconds=60, burst=0)

        @app.get("/limited")
        async def limited(request):
            return Response.json({"ok": True})

        client = TestClient(app)
        # First 2 requests succeed
        client.get("/limited")
        client.get("/limited")
        # 3rd should be blocked
        resp = client.get("/limited")
        assert resp.status == 429


class TestLoggingMiddleware:
    def test_request_completes_normally(self):
        app = Nexus()
        app.add_middleware(LoggingMiddleware)

        @app.get("/log-test")
        async def handler(request):
            return Response.json({"logged": True})

        client = TestClient(app)
        resp = client.get("/log-test")
        assert resp.status == 200

    def test_excluded_path(self):
        app = Nexus()
        app.add_middleware(LoggingMiddleware, exclude_paths=["/health"])

        @app.get("/health")
        async def health(request):
            return Response.json({"status": "ok"})

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status == 200
