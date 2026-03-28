"""Tests for nexus/core — routing, request, response, ASGI dispatch."""

import json
import pytest

from nexus import Nexus, Request, Response
from nexus.core.response import JSONResponse, HTMLResponse, ErrorResponse
from nexus.core.routing import Router, _compile_path
from tests.helpers import TestClient


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

class TestPathCompilation:
    def test_simple_path(self):
        regex, params = _compile_path("/users")
        assert regex.match("/users") is not None
        assert regex.match("/users/1") is None
        assert params == []

    def test_param_path(self):
        regex, params = _compile_path("/users/{id}")
        m = regex.match("/users/42")
        assert m is not None
        assert m.group("id") == "42"
        assert params == ["id"]

    def test_typed_param(self):
        regex, params = _compile_path("/items/{id:int}")
        assert regex.match("/items/99") is not None
        assert regex.match("/items/abc") is None

    def test_multi_param(self):
        regex, params = _compile_path("/orgs/{org}/repos/{repo}")
        m = regex.match("/orgs/nexus/repos/core")
        assert m is not None
        assert m.group("org") == "nexus"
        assert m.group("repo") == "core"
        assert params == ["org", "repo"]


class TestRouter:
    def test_register_and_match(self):
        router = Router()

        @router.get("/ping")
        async def ping(request): ...

        result = router.match("/ping", "GET")
        assert result is not None
        route, params = result
        assert route.handler is ping
        assert params == {}

    def test_method_mismatch(self):
        router = Router()

        @router.post("/submit")
        async def submit(request): ...

        assert router.match("/submit", "GET") is None

    def test_prefix(self):
        router = Router(prefix="/api/v1")

        @router.get("/users")
        async def users(request): ...

        result = router.match("/api/v1/users", "GET")
        assert result is not None


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class TestRequest:
    def _make_request(self, method="GET", path="/", headers=None, body=b"", qs=""):
        from tests.helpers import MockReceive
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": qs.encode(),
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": ("127.0.0.1", 1234),
        }
        return Request(scope, MockReceive(body))

    def test_method_and_path(self):
        req = self._make_request("GET", "/hello")
        assert req.method == "GET"
        assert req.path == "/hello"

    def test_headers(self):
        req = self._make_request(headers={"Content-Type": "application/json"})
        assert req.headers["content-type"] == "application/json"

    def test_query_params(self):
        req = self._make_request(qs="page=2&limit=10")
        assert req.query_params["page"] == "2"
        assert req.query("limit") == "10"
        assert req.query("missing") is None

    @pytest.mark.asyncio
    async def test_body(self):
        req = self._make_request(body=b"hello world")
        body = await req.body()
        assert body == b"hello world"

    @pytest.mark.asyncio
    async def test_json_body(self):
        payload = json.dumps({"key": "val"}).encode()
        req = self._make_request(body=payload, headers={"Content-Type": "application/json"})
        data = await req.json()
        assert data == {"key": "val"}


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class TestResponse:
    def test_json_response(self):
        r = Response.json({"ok": True})
        assert isinstance(r, JSONResponse)
        assert r.status_code == 200
        assert b'"ok": true' in r._body or b'"ok":true' in r._body

    def test_html_response(self):
        r = Response.html("<h1>Hi</h1>")
        assert isinstance(r, HTMLResponse)
        assert r.content_type == "text/html; charset=utf-8"

    def test_redirect(self):
        r = Response.redirect("/new-path")
        assert r.status_code == 302
        assert r.headers["location"] == "/new-path"

    def test_error_response(self):
        r = ErrorResponse("Not found", status_code=404, code="NOT_FOUND")
        assert r.status_code == 404

    def test_custom_status(self):
        r = Response.json({"created": True}, status_code=201)
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# ASGI app dispatch
# ---------------------------------------------------------------------------

class TestNexusApp:
    def test_get_route(self):
        app = Nexus(debug=True)

        @app.get("/hello")
        async def hello(request: Request):
            return Response.json({"message": "hello"})

        client = TestClient(app)
        resp = client.get("/hello")
        assert resp.status == 200
        assert resp.json()["message"] == "hello"

    def test_404(self):
        app = Nexus()
        client = TestClient(app)
        resp = client.get("/nonexistent")
        assert resp.status == 404

    def test_path_params(self):
        app = Nexus()

        @app.get("/users/{id}")
        async def get_user(request: Request, id: int):
            return Response.json({"id": id})

        client = TestClient(app)
        resp = client.get("/users/42")
        assert resp.status == 200
        assert resp.json()["id"] == 42

    def test_post_with_body(self):
        app = Nexus()

        @app.post("/echo")
        async def echo(request: Request):
            data = await request.json()
            return Response.json(data)

        client = TestClient(app)
        resp = client.post("/echo", body={"name": "Alice"})
        assert resp.status == 200
        assert resp.json()["name"] == "Alice"

    def test_sub_router(self):
        app = Nexus()
        router = Router(prefix="/api")

        @router.get("/status")
        async def status(request):
            return Response.json({"status": "ok"})

        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/api/status")
        assert resp.status == 200

    def test_docs_endpoint(self):
        app = Nexus(docs_url="/docs")

        @app.get("/ping")
        async def ping(request):
            return Response.text("pong")

        client = TestClient(app)
        resp = client.get("/docs")
        assert resp.status == 200
        assert b"swagger" in resp.body.lower()
