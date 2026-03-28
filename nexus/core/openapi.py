"""OpenAPI 3.0 schema generation + Swagger UI serving."""

from __future__ import annotations

import json
import re
from typing import Any

from nexus.core.routing import Route


_PARAM_RE = re.compile(r"\{(\w+)(?::([^}]+))?\}")

_TYPE_MAP = {
    "int": "integer",
    "float": "number",
    "str": "string",
    "uuid": "string",
    "path": "string",
    "bool": "boolean",
}

SWAGGER_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <title>{title} – Swagger UI</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" >
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"> </script>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"> </script>
<script>
window.onload = function() {{
  SwaggerUIBundle({{
    url: "{openapi_url}",
    dom_id: '#swagger-ui',
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
    layout: "StandaloneLayout",
    deepLinking: true,
    showExtensions: true,
    showCommonExtensions: true
  }})
}}
</script>
</body>
</html>
"""

REDOC_HTML = """\
<!DOCTYPE html>
<html>
  <head>
    <title>{title} – ReDoc</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>body {{ margin: 0; padding: 0; }}</style>
  </head>
  <body>
    <redoc spec-url="{openapi_url}"></redoc>
    <script src="https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js"></script>
  </body>
</html>
"""


def _extract_path_params(path: str) -> list[dict]:
    params = []
    for m in _PARAM_RE.finditer(path):
        name = m.group(1)
        type_hint = m.group(2) or "str"
        params.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": _TYPE_MAP.get(type_hint, "string")},
            }
        )
    return params


def _openapi_path(path: str) -> str:
    """Convert {id:int} → {id}."""
    return _PARAM_RE.sub(lambda m: "{" + m.group(1) + "}", path)


def generate_openapi_schema(
    routes: list[Route],
    *,
    title: str = "Nexus API",
    version: str = "1.0.0",
    description: str = "",
    servers: list[dict] | None = None,
) -> dict[str, Any]:
    paths: dict[str, Any] = {}

    for route in routes:
        openapi_path = _openapi_path(route.path)
        path_params = _extract_path_params(route.path)

        for method in route.methods:
            if method in ("HEAD", "WS"):
                continue
            path_item = paths.setdefault(openapi_path, {})
            operation: dict[str, Any] = {
                "summary": route.summary or route.name or "",
                "operationId": f"{method.lower()}_{(route.name or route.path).replace('/', '_').strip('_')}",
                "tags": route.tags or [],
                "parameters": path_params,
                "responses": {
                    "200": {"description": "Successful response"},
                    "422": {"description": "Validation error"},
                    "500": {"description": "Internal server error"},
                },
            }
            if route.description:
                operation["description"] = route.description
            if route.deprecated:
                operation["deprecated"] = True
            if method in ("POST", "PUT", "PATCH"):
                operation["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"type": "object"},
                        }
                    },
                }
            path_item[method.lower()] = operation

    schema: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {
            "title": title,
            "version": version,
            "description": description,
        },
        "paths": paths,
    }
    if servers:
        schema["servers"] = servers

    return schema


class OpenAPIEndpoints:
    """Mixin that adds /docs, /redoc, and /openapi.json to a Nexus app."""

    def mount_docs(
        self,
        routes: list[Route],
        *,
        title: str = "Nexus API",
        version: str = "1.0.0",
        description: str = "",
        docs_url: str = "/docs",
        redoc_url: str = "/redoc",
        openapi_url: str = "/openapi.json",
    ) -> None:
        schema = generate_openapi_schema(
            routes, title=title, version=version, description=description
        )
        schema_json = json.dumps(schema, indent=2)
        swagger_html = SWAGGER_HTML.format(title=title, openapi_url=openapi_url)
        redoc_html = REDOC_HTML.format(title=title, openapi_url=openapi_url)

        from nexus.core.response import HTMLResponse, Response

        async def serve_openapi(request):
            return Response(schema_json, content_type="application/json")

        async def serve_docs(request):
            return HTMLResponse(swagger_html)

        async def serve_redoc(request):
            return HTMLResponse(redoc_html)

        self.get(openapi_url, summary="OpenAPI JSON schema", tags=["_docs"])(serve_openapi)
        self.get(docs_url, summary="Swagger UI", tags=["_docs"])(serve_docs)
        self.get(redoc_url, summary="ReDoc UI", tags=["_docs"])(serve_redoc)
