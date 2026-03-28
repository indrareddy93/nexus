"""Tests for nexus/di — dependency injection."""

import pytest
from nexus.di.dependencies import DIContainer, Depends, Injectable
from nexus.core.request import Request
from tests.helpers import MockReceive


def make_request(path="/", method="GET", qs=""):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": qs.encode(),
        "headers": [],
        "client": ("127.0.0.1", 1),
    }
    return Request(scope, MockReceive())


class TestDepends:
    def test_repr(self):
        def my_dep(): ...
        d = Depends(my_dep)
        assert "my_dep" in repr(d)

    @pytest.mark.asyncio
    async def test_simple_dependency(self):
        container = DIContainer()

        def get_value():
            return 42

        async def handler(val=Depends(get_value)):
            return val

        req = make_request()
        result = await container.resolve_handler(handler, path_params={}, request=req)
        assert result == 42

    @pytest.mark.asyncio
    async def test_async_dependency(self):
        container = DIContainer()

        async def get_db():
            return {"connected": True}

        async def handler(db=Depends(get_db)):
            return db["connected"]

        req = make_request()
        result = await container.resolve_handler(handler, path_params={}, request=req)
        assert result is True

    @pytest.mark.asyncio
    async def test_generator_dependency(self):
        container = DIContainer()
        cleaned_up = []

        def get_resource():
            resource = {"open": True}
            yield resource
            cleaned_up.append(True)

        async def handler(res=Depends(get_resource)):
            return res["open"]

        req = make_request()
        result = await container.resolve_handler(handler, path_params={}, request=req)
        assert result is True
        assert cleaned_up == [True]

    @pytest.mark.asyncio
    async def test_nested_dependencies(self):
        container = DIContainer()

        def config():
            return {"secret": "abc"}

        def auth(cfg=Depends(config)):
            return cfg["secret"]

        async def handler(token=Depends(auth)):
            return token

        req = make_request()
        result = await container.resolve_handler(handler, path_params={}, request=req)
        assert result == "abc"

    @pytest.mark.asyncio
    async def test_path_param_injection(self):
        container = DIContainer()

        async def handler(id: int):
            return id * 2

        req = make_request()
        result = await container.resolve_handler(handler, path_params={"id": "5"}, request=req)
        assert result == 10

    @pytest.mark.asyncio
    async def test_request_injection(self):
        container = DIContainer()

        async def handler(request: Request):
            return request.path

        req = make_request(path="/test-path")
        result = await container.resolve_handler(handler, path_params={}, request=req)
        assert result == "/test-path"


class TestDIContainer:
    @pytest.mark.asyncio
    async def test_register_and_resolve(self):
        container = DIContainer()

        class MyService:
            def value(self):
                return "service"

        container.register(MyService)
        instance = await container.resolve(MyService)
        assert instance.value() == "service"

    @pytest.mark.asyncio
    async def test_singleton_behaviour(self):
        container = DIContainer()

        class Counter:
            count = 0
            def __init__(self):
                Counter.count += 1

        container.register(Counter)
        a = await container.resolve(Counter)
        b = await container.resolve(Counter)
        assert a is b
        assert Counter.count == 1

    @pytest.mark.asyncio
    async def test_register_instance(self):
        container = DIContainer()

        class DB:
            pass

        db = DB()
        container.register_instance(DB, db)
        resolved = await container.resolve(DB)
        assert resolved is db

    @pytest.mark.asyncio
    async def test_unregistered_raises(self):
        container = DIContainer()

        class Unknown:
            pass

        with pytest.raises(LookupError):
            await container.resolve(Unknown)
