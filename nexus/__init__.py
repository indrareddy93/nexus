"""
Nexus Framework
~~~~~~~~~~~~~~~

A next-generation Python ASGI web framework:
  - Django completeness
  - Flask simplicity
  - FastAPI performance
  - AI-native by default

Basic usage::

    from nexus import Nexus, Request, Response

    app = Nexus()

    @app.get("/")
    async def index(request: Request) -> Response:
        return Response.json({"message": "Hello from Nexus!"})

:copyright: (c) 2024 Nexus Contributors
:license: MIT
"""

from nexus.core.app import Nexus
from nexus.core.request import Request
from nexus.core.response import Response, JSONResponse, HTMLResponse, StreamingResponse
from nexus.core.routing import Router, include_router
from nexus.di.dependencies import Depends, DIContainer, Injectable

__all__ = [
    "Nexus",
    "Request",
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "StreamingResponse",
    "Router",
    "include_router",
    "Depends",
    "DIContainer",
    "Injectable",
]

__version__ = "0.1.0"
