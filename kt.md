# Nexus Framework — Knowledge Transfer (KT) Document

> Complete technical reference for the Nexus Framework — architecture, module internals, APIs, extension points, and operational runbook.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Architecture](#3-architecture)
4. [Core Engine (`nexus/core`)](#4-core-engine)
5. [Middleware (`nexus/middleware`)](#5-middleware)
6. [Dependency Injection (`nexus/di`)](#6-dependency-injection)
7. [ORM (`nexus/orm`)](#7-orm)
8. [Authentication (`nexus/auth`)](#8-authentication)
9. [Cache (`nexus/cache`)](#9-cache)
10. [Background Tasks (`nexus/tasks`)](#10-background-tasks)
11. [WebSocket (`nexus/websocket`)](#11-websocket)
12. [AI Module (`nexus/ai`)](#12-ai-module)
13. [CLI (`nexus/cli`)](#13-cli)
14. [Testing](#14-testing)
15. [CI/CD Pipeline](#15-cicd-pipeline)
16. [Configuration Reference](#16-configuration-reference)
17. [Deployment](#17-deployment)
18. [Extension Guide](#18-extension-guide)
19. [Troubleshooting](#19-troubleshooting)

---

## 1. Project Overview

**Nexus** is a production-grade Python ASGI web framework that combines:

| Goal | Inspired by |
|------|------------|
| Django completeness | Full-stack batteries included |
| Flask simplicity | Decorator-based, minimal boilerplate |
| FastAPI performance | 100% async, ASGI-native |
| AI-native design | Built-in LLM/RAG/embedding support |

### Key Facts

- **Language:** Python 3.11+
- **Protocol:** ASGI (Uvicorn / Hypercorn compatible)
- **Zero mandatory runtime dependencies** — everything is optional
- **120 tests**, all passing on Python 3.11, 3.12, 3.13
- **Pure Python** — no C extensions required for core features

---

## 2. Repository Structure

```
nexus_framework/
├── nexus/                        # Framework source
│   ├── __init__.py               # Public API re-exports
│   ├── core/
│   │   ├── app.py                # Nexus ASGI application class
│   │   ├── request.py            # HTTP Request abstraction
│   │   ├── response.py           # Response, JSONResponse, HTMLResponse, StreamingResponse
│   │   ├── routing.py            # Router, Route, path param compiler
│   │   └── openapi.py            # OpenAPI 3.0 schema + Swagger/ReDoc UI
│   ├── middleware/
│   │   ├── base.py               # BaseMiddleware class
│   │   ├── cors.py               # CORSMiddleware
│   │   ├── rate_limit.py         # RateLimitMiddleware (sliding window)
│   │   └── logging.py            # LoggingMiddleware (structured access log)
│   ├── di/
│   │   └── dependencies.py       # Depends(), DIContainer, Injectable
│   ├── orm/
│   │   ├── base.py               # ModelMeta metaclass, Model base class
│   │   ├── fields.py             # Field descriptors (Int, Str, Bool, DateTime, JSON…)
│   │   └── manager.py            # ModelManager, QueryBuilder, AsyncSQLiteConnection
│   ├── auth/
│   │   ├── jwt.py                # JWT create/decode/refresh, JWTAuth, jwt_required()
│   │   └── rbac.py               # RBACPolicy, Role, Permission, requires_role/permission
│   ├── cache/
│   │   └── memory.py             # Cache (TTL), @cached decorator
│   ├── tasks/
│   │   └── queue.py              # TaskQueue, Task, TaskStatus, @task decorator
│   ├── websocket/
│   │   └── connection.py         # WebSocketConnection, WebSocketRoom, RoomManager
│   ├── ai/
│   │   ├── engine.py             # AIEngine (OpenAI / Anthropic / Ollama / Groq)
│   │   ├── embeddings.py         # EmbeddingEngine, cosine similarity, vector store
│   │   ├── rag.py                # RAGPipeline, RAGResponse
│   │   └── middleware.py         # AIMiddleware (classify / summarize)
│   └── cli/
│       └── main.py               # nexus new / nexus run / nexus routes
│
├── tests/
│   ├── helpers.py                # MockReceive, MockSend, TestClient
│   ├── test_core.py              # 16 tests — routing, request, response, ASGI
│   ├── test_di.py                # 11 tests — DI container
│   ├── test_orm.py               # 15 tests — ORM CRUD + query builder
│   ├── test_auth.py              # 14 tests — JWT + RBAC
│   ├── test_cache.py             # 11 tests — cache + decorator
│   ├── test_tasks.py             #  6 tests — queue, retry, scheduler
│   ├── test_websocket.py         # 13 tests — WS connection + rooms
│   ├── test_ai.py                # 16 tests — embeddings, RAG, engine
│   └── test_middleware.py        #  6 tests — CORS, rate limit, logging
│
├── app.py                        # Full-featured demo application
├── kt.md                         # This document
├── README.md                     # Quick-start README
├── pyproject.toml                # Build config + tool config
├── requirements.txt              # Runtime deps
├── requirements-dev.txt          # Dev/test deps
├── Dockerfile                    # Production container image
└── .github/workflows/ci.yml      # GitHub Actions CI
```

---

## 3. Architecture

```
HTTP/WS Request
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│                   ASGI Core Engine                       │
│  scope: {type, method, path, headers, query_string}      │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────▼──────────────────┐
        │        Middleware Stack          │
        │  (built once, applied per req)   │
        │  ┌─────────┐ ┌──────────────┐   │
        │  │  CORS   │ │ Rate Limiter │   │
        │  └─────────┘ └──────────────┘   │
        │  ┌─────────┐ ┌──────────────┐   │
        │  │ Logging │ │   Custom     │   │
        │  └─────────┘ └──────────────┘   │
        └──────────────┬──────────────────┘
                       │
        ┌──────────────▼──────────────────┐
        │          Router.match()          │
        │  Regex match → Route + params    │
        └──────────────┬──────────────────┘
                       │
        ┌──────────────▼──────────────────┐
        │      DIContainer.resolve()       │
        │  Injects: request, path_params,  │
        │  query_params, body, Depends()   │
        └──────────────┬──────────────────┘
                       │
        ┌──────────────▼──────────────────┐
        │         Route Handler            │
        │   async def handler(...) -> ...  │
        └──────────────┬──────────────────┘
                       │
        ┌──────────────▼──────────────────┐
        │      Response.__call__()         │
        │  ASGI send events: start + body  │
        └─────────────────────────────────┘
```

### Request Lifecycle

1. **ASGI receive** — Uvicorn calls `app(scope, receive, send)`
2. **Lifespan** — `startup` hooks run once on server start
3. **Middleware chain** — instantiated once, applied to every request
4. **Routing** — regex match, path params extracted
5. **DI resolution** — all parameters auto-resolved (lazy, cached per-request)
6. **Handler execution** — your `async def` runs
7. **Response send** — ASGI `http.response.start` + `http.response.body`
8. **Generator cleanup** — `Depends()` generator `finally` blocks run

---

## 4. Core Engine

### `Nexus` class (`nexus/core/app.py`)

The main application object. Extends both `Router` and `OpenAPIEndpoints`.

```python
from nexus import Nexus

app = Nexus(
    title="My API",          # Shown in Swagger UI
    version="1.0.0",
    description="...",
    docs_url="/docs",        # Swagger UI path
    redoc_url="/redoc",      # ReDoc path
    openapi_url="/openapi.json",
    debug=False,             # Shows full tracebacks in 500 responses
)
```

#### Route Registration

```python
@app.get("/users/{id:int}")
async def get_user(request: Request, id: int) -> Response:
    return Response.json({"id": id})

# All HTTP verbs supported:
@app.post("/users")
@app.put("/users/{id}")
@app.patch("/users/{id}")
@app.delete("/users/{id}")
@app.head("/users")
@app.options("/users")

# WebSocket
@app.ws("/chat/{room}")
async def chat(ws: WebSocketConnection): ...
```

#### Path Parameter Type Converters

| Syntax | Regex | Python type |
|--------|-------|-------------|
| `{id}` or `{id:str}` | `[^/]+` | `str` |
| `{id:int}` | `[0-9]+` | `int` |
| `{id:float}` | `[0-9]*\.?[0-9]+` | `float` |
| `{id:uuid}` | UUID pattern | `str` |
| `{rest:path}` | `.+` (matches slashes) | `str` |

#### Lifecycle Hooks

```python
@app.on_startup
async def startup():
    await db.connect()

@app.on_shutdown
async def shutdown():
    await db.close()

# Or pass at construction:
app = Nexus(on_startup=[startup_fn], on_shutdown=[shutdown_fn])
```

#### Sub-Routers

```python
from nexus.core.routing import Router

v1 = Router(prefix="/api/v1", tags=["v1"])

@v1.get("/users")
async def list_users(request): ...

app.include_router(v1)
```

### `Request` (`nexus/core/request.py`)

| Property / Method | Description |
|---|---|
| `request.method` | `"GET"`, `"POST"`, etc. |
| `request.path` | `/api/users/1` |
| `request.headers` | `dict[str, str]` (lowercase keys) |
| `request.query_params` | Parsed query string dict |
| `request.query("key")` | Single query param |
| `request.path_params` | Dict set by router |
| `request.client` | `(ip, port)` tuple |
| `await request.body()` | Raw `bytes` |
| `await request.text()` | Body as `str` |
| `await request.json()` | Parsed JSON |
| `await request.form()` | URL-encoded form data |
| `request.state` | Per-request mutable dict |

### `Response` (`nexus/core/response.py`)

```python
# Factory methods
Response.json({"key": "val"}, status_code=200)
Response.html("<h1>Hello</h1>")
Response.text("plain text")
Response.redirect("/new-path", status_code=302)
Response.no_content()          # 204

# Direct construction
Response(body, status_code=200, headers={}, content_type="text/plain")

# Streaming
async def gen():
    for i in range(10):
        yield f"data: {i}\n\n"

StreamingResponse(gen(), content_type="text/event-stream")
```

### OpenAPI (`nexus/core/openapi.py`)

Auto-mounted on first HTTP request. Reads all registered routes and generates:

- `/openapi.json` — OpenAPI 3.0 spec
- `/docs` — Swagger UI (served from CDN)
- `/redoc` — ReDoc UI (served from CDN)

Annotate routes with metadata:

```python
@app.get(
    "/users",
    tags=["users"],
    summary="List all users",
    description="Returns paginated user list",
    response_model=UserSchema,
    deprecated=False,
)
async def list_users(request): ...
```

---

## 5. Middleware

### How the middleware stack works

Middlewares are **class-based** and instantiated **once** when the first request arrives. Each wraps the next handler in the chain (outermost registered = outermost executed).

```
Request → LoggingMW → RateLimitMW → CORSMw → dispatch → Response
```

### Registering Middleware

```python
# Class-based (recommended)
app.add_middleware(CORSMiddleware, allow_origins=["*"])
app.add_middleware(RateLimitMiddleware, requests_per_window=100)
app.add_middleware(LoggingMiddleware)

# Function-based
@app.use
async def my_middleware(request: Request, call_next) -> Response:
    print(f"Before: {request.path}")
    response = await call_next(request)
    print(f"After: {response.status_code}")
    return response
```

### Writing Custom Middleware

```python
from nexus.middleware.base import BaseMiddleware
from nexus.core.request import Request
from nexus.core.response import Response
import time

class TimingMiddleware(BaseMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time"] = f"{elapsed:.2f}ms"
        return response

app.add_middleware(TimingMiddleware)
```

### `CORSMiddleware`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],  # or ["*"]
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
    expose_headers=["X-Custom-Header"],
    max_age=86400,
)
```

### `RateLimitMiddleware`

Uses a **sliding window** algorithm per client IP.

```python
app.add_middleware(
    RateLimitMiddleware,
    requests_per_window=100,    # Max requests
    window_seconds=60.0,        # Window size
    burst=20,                   # Extra allowed above limit
    exempt_paths=["/health", "/docs"],
)
```

Response headers added: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

Returns `429 Too Many Requests` with `Retry-After` header when exceeded.

### `LoggingMiddleware`

```python
import logging
app.add_middleware(
    LoggingMiddleware,
    log_level=logging.INFO,
    exclude_paths=["/health", "/ping"],
    log_body=False,
)
```

Log format: `METHOD /path STATUS 12.34ms [127.0.0.1]`

---

## 6. Dependency Injection

### `Depends()`

Works identically to FastAPI's `Depends()`.

```python
from nexus.di.dependencies import Depends

# Simple value dependency
def get_settings():
    return {"debug": True, "db_url": "sqlite:///app.db"}

@app.get("/config")
async def config(settings=Depends(get_settings)):
    return Response.json(settings)
```

### Generator Dependencies (with cleanup)

```python
async def get_db():
    db = ModelManager("sqlite:///app.db")
    await db.connect()
    try:
        yield db          # Handler receives this value
    finally:
        await db.close()  # Runs after handler returns

@app.get("/users")
async def list_users(db=Depends(get_db)):
    users = await db.query(User).all()
    return Response.json([u.to_dict() for u in users])
```

### Nested Dependencies

```python
def get_config():
    return {"secret": "my-secret"}

def get_auth(config=Depends(get_config)):
    return JWTAuth(secret=config["secret"])

async def get_current_user(auth=Depends(get_auth)):
    # ...
    pass

@app.get("/me")
async def me(user=Depends(get_current_user)):
    return Response.json(user.to_dict())
```

### DIContainer (service registration)

```python
class EmailService:
    async def send(self, to: str, subject: str): ...

app.register(EmailService)           # Singleton by class
app.register_instance(EmailService, EmailService())  # Pre-built instance

# Resolve manually
service = await app.container.resolve(EmailService)
```

### Auto-injection priority

1. Parameter named `request` → the `Request` object
2. Parameter with `Depends(fn)` default → resolved recursively
3. Parameter name matches a path param → type-cast and injected
4. Parameter name matches a query param → type-cast and injected
5. POST/PUT/PATCH body JSON field with matching name → injected
6. Parameter has a default value → used as-is

---

## 7. ORM

### Model Definition

```python
from nexus.orm import Model, IntField, StrField, BoolField, FloatField
from nexus.orm import DateTimeField, JSONField, TextField

class Product(Model):
    __table__ = "products"          # Optional — defaults to snake_case class name + 's'

    id          = IntField(primary_key=True)
    name        = StrField(max_length=200, nullable=False)
    description = TextField()
    price       = FloatField(nullable=False)
    in_stock    = BoolField(default=True)
    metadata    = JSONField()       # Serialised to TEXT, returns dict
    created_at  = DateTimeField(auto_now_add=True)
    updated_at  = DateTimeField(auto_now=True)
```

### Field Types Reference

| Field class | SQLite type | Notes |
|---|---|---|
| `IntField` | `INTEGER` | `primary_key=True` → AUTOINCREMENT |
| `StrField(max_length=N)` | `VARCHAR(N)` / `TEXT` | |
| `TextField` | `TEXT` | No length limit |
| `BoolField` | `INTEGER` | Stored as 0/1 |
| `FloatField` | `REAL` | |
| `DateTimeField` | `TEXT` | ISO-8601; `auto_now_add`, `auto_now` |
| `JSONField` | `TEXT` | Serialised with `json.dumps` |

### ModelManager (database operations)

```python
from nexus.orm import ModelManager

db = ModelManager("sqlite:///app.db")

# Connect on app startup
await db.connect()

# Create tables
await db.create_tables(User, Product, Order)

# Drop tables
await db.drop_tables(TempTable)

# Close on app shutdown
await db.close()
```

### CRUD Operations

```python
# Create
user = await db.create(User, name="Alice", email="alice@example.com")

# Save (upsert)
user.name = "Alice Smith"
await db.save(user)

# Get by PK
user = await db.get(User, pk=1)           # Returns None if not found
user = await db.get_or_404(User, pk=999)  # Raises ValueError if not found

# Get or create
user, created = await db.get_or_create(User, email="bob@example.com")

# Delete
await db.delete(user)

# Bulk create
users = [User(name=f"User {i}") for i in range(100)]
await db.bulk_create(users)

# Raw SQL
rows = await db.execute_raw("SELECT COUNT(*) as n FROM users WHERE is_active = ?", (1,))
```

### Query Builder

Chainable, lazy — nothing executes until a terminal method is called.

```python
qb = db.query(User)

# Filtering
.filter(is_active=True)              # WHERE is_active = 1
.filter(age__gt=18)                  # WHERE age > 18
.filter(age__gte=18)                 # WHERE age >= 18
.filter(age__lt=65)                  # WHERE age < 65
.filter(age__lte=65)                 # WHERE age <= 65
.filter(name__like="%alice%")        # WHERE name LIKE '%alice%'
.filter(status__ne="banned")         # WHERE status != 'banned'
.filter(id__in=[1, 2, 3])           # WHERE id IN (1, 2, 3)
.filter(id__not_in=[4, 5])          # WHERE id NOT IN (4, 5)
.filter(deleted_at__is_null=True)    # WHERE deleted_at IS NULL
.where("created_at > ?", "2024-01-01")  # Raw condition

# Ordering
.order_by("created_at", desc=True)

# Pagination
.limit(20).offset(40)

# Terminal methods
await qb.all()       # list[Model]
await qb.first()     # Model | None
await qb.last()      # Model | None
await qb.count()     # int
await qb.exists()    # bool
await qb.delete()    # int (rows deleted)
await qb.update(is_active=False)  # int (rows updated)
```

---

## 8. Authentication

### JWT (JSON Web Tokens)

Implemented in pure Python — no `PyJWT` or `python-jose` required.

```python
from nexus.auth.jwt import JWTAuth, create_token, decode_token, JWTError

# Functional API
token = create_token(
    {"sub": "user_123", "role": "admin"},
    secret="my-secret",
    expires_in=3600,   # seconds
)
claims = decode_token(token, secret="my-secret")
# {"sub": "user_123", "role": "admin", "iat": 1700000000, "exp": 1700003600}

# Class API
auth = JWTAuth(secret="my-secret", expires_in=3600)
token = auth.create({"sub": user.id})
claims = auth.decode(token)
new_token = auth.refresh(token)   # Issues new token from existing claims
```

### `jwt_required()` — DI guard

```python
from nexus.auth.jwt import jwt_required

SECRET = "my-secret"

@app.get("/me")
async def me(claims=jwt_required(SECRET)):
    return Response.json({"user_id": claims["sub"], "role": claims["role"]})
```

Expects `Authorization: Bearer <token>` header. Raises `PermissionError` (→ 500) on failure — wrap in try/except or handle via middleware for a clean 401.

### RBAC (Role-Based Access Control)

```python
from nexus.auth.rbac import RBACPolicy, requires_role, requires_permission

rbac = RBACPolicy()

# Define roles
rbac.define_role("admin",   permissions={"*"})         # Wildcard = everything
rbac.define_role("editor",  permissions={"articles:read", "articles:write"})
rbac.define_role("viewer",  permissions={"articles:read"})

# Role inheritance
rbac.define_role(
    "senior_editor",
    permissions={"articles:publish"},
    inherits=["editor"],    # Inherits all editor permissions
)

# Wildcard per resource
rbac.define_role("content_mgr", permissions={"content:*"})

# Check programmatically
rbac.has_permission("editor", "articles:write")   # True
rbac.has_permission("viewer", "articles:write")   # False
rbac.all_permissions("senior_editor")             # All effective perms

# DI guards
@app.delete("/users/{id}")
async def delete_user(id: int, _=requires_role("admin")):
    ...

@app.post("/articles")
async def create_article(body=Body(), _=requires_permission("articles:write", policy=rbac)):
    ...
```

---

## 9. Cache

### `Cache` class

```python
from nexus.cache.memory import Cache

cache = Cache(
    default_ttl=300,     # seconds; 0 = never expire
    max_size=10_000,     # entries before LRU eviction
)

# Basic operations
cache.set("key", value, ttl=60)
value = cache.get("key", default=None)
cache.has("key")        # bool
cache.delete("key")     # bool
cache.clear()

# Async compute-and-cache
result = await cache.get_or_set("expensive_key", async_compute_fn, ttl=120)

# Maintenance
cache.evict_expired()   # Returns count removed
cache.stats()           # {"total": N, "active": N, "expired": N}
cache.size()            # int
```

### `@cached` decorator

```python
from nexus.cache.memory import cached

cache = Cache(default_ttl=60)

@app.get("/products")
@cached(cache, ttl=120)
async def list_products(request):
    return Response.json(await db.query(Product).all())

# Custom cache key
@app.get("/products/{id}")
@cached(cache, key_fn=lambda req: f"product:{req.path_params['id']}")
async def get_product(request, id: int):
    product = await db.get(Product, id)
    return Response.json(product.to_dict())

# Static key
@app.get("/config")
@cached(cache, key="app:config", ttl=3600)
async def get_config(request): ...
```

---

## 10. Background Tasks

### `TaskQueue`

```python
from nexus.tasks.queue import TaskQueue, TaskStatus

queue = TaskQueue(workers=4, max_queue_size=1000)

# Lifecycle — call in startup/shutdown hooks
await queue.start()
await queue.stop(timeout=10.0)   # Drains queue before stopping
```

### Enqueueing Tasks

```python
# Enqueue by function reference
task_id = await queue.enqueue(
    send_email,
    "user@example.com",        # positional args
    subject="Welcome",         # keyword args
    max_retries=3,
    retry_delay=1.0,           # doubles each retry (exponential backoff)
)

# Non-blocking (raises QueueFull if at capacity)
task_id = queue.enqueue_nowait(send_notification, user_id=42)
```

### `@task` Decorator

```python
from nexus.tasks.queue import task

@task(queue, max_retries=5, retry_delay=2.0)
async def process_payment(order_id: int, amount: float):
    # ... payment processing logic
    pass

# Calling the decorated function enqueues it automatically
task_id = await process_payment(order_id=123, amount=99.99)
```

### Scheduling Recurring Tasks

```python
# Every 3600 seconds (1 hour)
queue.schedule(
    cleanup_expired_tokens,
    interval=3600,
    run_immediately=False,
)

# With args
queue.schedule(
    sync_to_external_api,
    interval=300,
    args=(endpoint_url,),
    kwargs={"auth_token": TOKEN},
)
```

### Task Status Tracking

```python
task = queue.get_task(task_id)
task.status        # TaskStatus.PENDING / RUNNING / SUCCESS / FAILED / RETRYING
task.result        # Return value on success
task.error         # Error string on failure
task.attempts      # Number of attempts made
task.elapsed       # Duration in seconds
task.to_dict()     # Serialisable dict

# List tasks
all_tasks   = queue.list_tasks(limit=100)
failed      = queue.list_tasks(status=TaskStatus.FAILED)

# Stats
queue.stats()
# {"total": 150, "queue_size": 3, "workers": 4, "by_status": {...}}
```

### Retry Behaviour

```
Attempt 1 fails → wait 1.0s
Attempt 2 fails → wait 2.0s
Attempt 3 fails → wait 4.0s
Attempt 4 fails → PERMANENT FAILURE (max_retries=3)
```

Delay formula: `retry_delay * (2 ** (attempt - 1))`

---

## 11. WebSocket

### Handler registration

```python
@app.ws("/ws/{channel}")
async def websocket_handler(ws: WebSocketConnection):
    await ws.accept()               # Complete handshake
    async for message in ws:        # Receive until disconnect
        await ws.send_text(message)
    # ws.close() called automatically
```

### `WebSocketConnection` API

```python
# Lifecycle
await ws.accept(subprotocol=None)
await ws.close(code=1000, reason="")

# Receive
text  = await ws.receive_text()     # str | None
data  = await ws.receive_json()     # Any | None
raw   = await ws.receive_raw()      # bytes | str | None
blob  = await ws.receive_bytes()    # bytes | None

# Send
await ws.send_text("hello")
await ws.send_json({"event": "update", "data": {...}})
await ws.send_bytes(b"\x00\x01")

# Metadata
ws.path         # "/ws/lobby"
ws.path_params  # {"channel": "lobby"}
ws.headers      # dict[str, str]
ws.client       # ("127.0.0.1", 12345)
ws.state        # mutable dict for per-connection data

# Async iteration
async for msg in ws:
    process(msg)
```

### `WebSocketRoom` — Pub/Sub

```python
from nexus.websocket.connection import WebSocketRoom

room = WebSocketRoom("chat-lobby")
room.add(ws)
room.remove(ws)
room.size               # int

# Broadcast
sent = await room.broadcast_text("hello everyone")     # Returns count sent
sent = await room.broadcast_json({"type": "message"})
sent = await room.broadcast_bytes(binary_data)
```

Dead connections are automatically removed on failed send.

### `RoomManager` — Multi-room

```python
from nexus.websocket.connection import RoomManager

rooms = RoomManager()

@app.ws("/chat/{room_id}")
async def chat(ws: WebSocketConnection):
    room = rooms.get_or_create(ws.path_params["room_id"])
    room.add(ws)
    try:
        async for message in ws:
            await room.broadcast_json({"from": "user", "text": message})
    finally:
        room.remove(ws)
        if room.size == 0:
            rooms.delete(ws.path_params["room_id"])

# Inspection
rooms.get("lobby")          # WebSocketRoom | None
rooms.all_rooms()           # list[WebSocketRoom]
rooms.stats()
# {"rooms": 5, "total_connections": 42, "room_details": {"lobby": 10, ...}}
```

---

## 12. AI Module

### `AIEngine` — LLM Interface

```python
from nexus.ai.engine import AIEngine, AIMessage

# OpenAI
ai = AIEngine(
    provider="openai",
    model="gpt-4o-mini",
    api_key="sk-...",
    system_prompt="You are a helpful assistant.",
    temperature=0.7,
    max_tokens=2048,
    timeout=120.0,
)

# Anthropic Claude
ai = AIEngine(provider="anthropic", model="claude-3-haiku-20240307", api_key="sk-ant-...")

# Local Ollama
ai = AIEngine(provider="ollama", model="llama3")

# Any OpenAI-compatible API (Groq, Together, etc.)
ai = AIEngine(provider="groq", model="llama3-8b-8192", api_key="gsk_...")
```

#### Generation methods

```python
# Single completion
response = await ai.generate("Explain async Python")
print(response.content)         # str
print(response.model)           # "gpt-4o-mini"
print(response.total_tokens)    # int
print(response.prompt_tokens)   # int

# Multi-turn chat
history = [
    AIMessage("user", "What is Nexus?"),
    AIMessage("assistant", "Nexus is a Python ASGI framework..."),
]
response = await ai.generate("Give me an example", messages=history)

# Full multi-turn without extra prompt
response = await ai.chat(history)

# Token streaming
async for token in ai.generate_stream("Write a poem about Python"):
    print(token, end="", flush=True)

# Embeddings (for manual use)
vector = await ai.embed("some text")   # list[float]
```

### `EmbeddingEngine` — Vector Store

```python
from nexus.ai.embeddings import EmbeddingEngine

# Mock provider (no API key needed — for dev/testing)
engine = EmbeddingEngine()

# OpenAI embeddings
engine = EmbeddingEngine(
    provider="openai",
    model="text-embedding-3-small",
    api_key="sk-...",
)

# Index documents
await engine.add_documents([
    {"text": "Python was created by Guido van Rossum", "metadata": {"source": "wiki"}, "doc_id": "doc1"},
    {"text": "Nexus is a fast async web framework",   "metadata": {"source": "docs"}, "doc_id": "doc2"},
])

await engine.add_text("Short text snippet", metadata={"type": "note"})

# Search
results = await engine.search("who created Python?", top_k=3, threshold=0.5)
for result in results:
    print(f"[{result.score:.3f}] {result.text}")
    print(f"  metadata: {result.metadata}")

# Manage
engine.count()   # int
engine.clear()
engine.stats()   # {"documents": N, "provider": "mock", ...}
```

### `RAGPipeline` — Retrieval-Augmented Generation

```python
from nexus.ai.rag import RAGPipeline

rag = RAGPipeline(
    ai=ai,
    embeddings=engine,
    top_k=5,
    score_threshold=0.3,
    prompt_template=None,   # Uses built-in default; or provide custom
)

# Build knowledge base
await rag.ingest([
    {"text": "...", "metadata": {"source": "docs"}},
])
await rag.ingest_text("Quick text snippet")

# Query
result = await rag.query("How does authentication work?")
print(result.answer)           # LLM-generated answer
print(result.query)            # Original question
print(result.model)            # LLM model used
for source in result.sources:
    print(f"[{source.score:.2f}] {source.text[:80]}")

# Batch
responses = await rag.batch_query(["Q1?", "Q2?", "Q3?"])

# Maintenance
rag.clear_knowledge_base()
rag.stats()   # {"documents": N, "top_k": 5, ...}

# Serialise result
result.to_dict()
```

### `AIMiddleware`

```python
from nexus.ai.middleware import AIMiddleware

app.add_middleware(
    AIMiddleware,
    ai=ai,
    classify_requests=True,            # Block suspicious/spam/bot requests
    summarize_responses=False,         # Add _ai_summary to JSON responses
    moderation_paths=["/api/submit"],  # Only moderate these paths
)
```

When `classify_requests=True`, the AI labels each request as `normal | suspicious | spam | bot`. Non-normal requests get a `403` response.

---

## 13. CLI

### `nexus new <name>` — Scaffold a project

```bash
nexus new myapi
cd myapi
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Creates:
```
myapi/
├── myapi/
│   ├── routes/api.py
│   ├── models/user.py
│   ├── services/
│   └── config.py
├── tests/test_app.py
├── app.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── .gitignore
└── .env.example
```

### `nexus run` — Dev server

```bash
nexus run                          # Default: 127.0.0.1:8000, --reload
nexus run --host 0.0.0.0           # Bind all interfaces
nexus run --port 8080
nexus run --no-reload              # Disable hot reload
nexus run --workers 4              # Multiple workers (no reload)
nexus run --app mymodule:myapp     # Custom module:attribute
```

### `nexus routes` — Inspect routes

```bash
nexus routes
# METHOD     PATH                       NAME                          TAGS
# --------------------------------------------------------------------------
# GET        /                          index                         meta
# POST       /auth/login                login                         auth
# GET        /users                     list_users                    users
# ...
```

---

## 14. Testing

### Running tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest tests/ -v

# Run specific module
pytest tests/test_orm.py -v

# Run with coverage
pytest tests/ --cov=nexus --cov-report=html

# Run a single test
pytest tests/test_auth.py::TestJWT::test_create_and_decode -v
```

### Test helpers (`tests/helpers.py`)

```python
from tests.helpers import TestClient, MockReceive, MockSend

client = TestClient(app)

# HTTP methods
resp = client.get("/users")
resp = client.post("/users", body={"name": "Alice"})
resp = client.put("/users/1", body={"name": "Alice Smith"})
resp = client.delete("/users/1")
resp = client.patch("/users/1", body={"is_active": False})

# With headers / query string
resp = client.get("/search", headers={"Authorization": f"Bearer {token}"}, query_string="q=python")

# Response inspection
resp.status          # int (HTTP status code)
resp.headers         # dict[str, str]
resp.body            # bytes
resp.json()          # parsed JSON
resp.text()          # str
```

### Writing async tests

```python
import pytest

@pytest.mark.asyncio
async def test_something():
    result = await some_async_fn()
    assert result == expected
```

### Test fixtures with database

```python
@pytest.fixture
async def db():
    manager = ModelManager("sqlite:///:memory:")
    await manager.connect()
    await manager.create_tables(User, Post)
    yield manager
    await manager.close()

class TestUserCRUD:
    @pytest.mark.asyncio
    async def test_create(self, db):
        user = await db.create(User, name="Alice", email="a@b.com")
        assert user.id is not None
```

---

## 15. CI/CD Pipeline

### GitHub Actions (`.github/workflows/ci.yml`)

```
Push to main/develop or PR to main
         │
    ┌────┴────┐
    │  test   │   Matrix: Python 3.11, 3.12, 3.13
    │         │   Steps:
    │         │   1. Checkout code
    │         │   2. Setup Python
    │         │   3. pip install -r requirements-dev.txt && pip install -e .
    │         │   4. ruff check nexus/ tests/
    │         │   5. mypy nexus/ (continue-on-error)
    │         │   6. pytest tests/ -v --tb=short
    └────┬────┘
         │
    ┌────┴────┐
    │security │   bandit -r nexus/ -ll (continue-on-error)
    └─────────┘
```

### Common CI failures and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `ruff check` fails | Lint errors in code | Run `.venv/Scripts/ruff check --fix nexus/ tests/` |
| `pytest` import error | Missing dependency | Add to `requirements-dev.txt` |
| `asyncio` deprecation | `get_event_loop()` used | Use `asyncio.run()` instead |
| `hmac.new` deprecation | Python 3.13 | Use `hmac.HMAC()` instead |
| pytest-asyncio warnings | Missing fixture scope | Add `asyncio_default_fixture_loop_scope = "function"` to pyproject.toml |

---

## 16. Configuration Reference

### `pyproject.toml` — Full reference

```toml
[project]
name = "nexus-framework"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
standard = ["uvicorn[standard]>=0.30.0", "httpx>=0.27.0"]
full = ["uvicorn[standard]>=0.30.0", "httpx>=0.27.0", "pyyaml>=6.0"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "ruff>=0.5.0", "mypy>=1.10", ...]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["."]
filterwarnings = ["ignore::DeprecationWarning"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]
ignore = ["B008", "E501"]

[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
```

### Environment Variables (demo app)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///app.db` | Database connection string |
| `JWT_SECRET` | `change-me` | JWT signing secret (change in prod!) |
| `DEBUG` | `false` | Enables full tracebacks in 500 responses |

---

## 17. Deployment

### Running locally

```bash
# Development (hot reload)
uvicorn app:app --reload --host 127.0.0.1 --port 8000

# Production (multiple workers)
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker

```bash
# Build image
docker build -t nexus-app .

# Run container
docker run -p 8000:8000 \
  -e JWT_SECRET=your-secret-here \
  -e DATABASE_URL=sqlite:///app.db \
  nexus-app

# With docker-compose
docker-compose up --build
```

### Production checklist

- [ ] Set a strong `JWT_SECRET` (min 32 chars, random)
- [ ] Set `DEBUG=false`
- [ ] Use PostgreSQL in production (not SQLite)
- [ ] Put a reverse proxy (Nginx/Caddy) in front of Uvicorn
- [ ] Set `allow_origins` to specific domains (not `["*"]`)
- [ ] Enable HTTPS / TLS termination at proxy
- [ ] Configure `RateLimitMiddleware` with appropriate limits
- [ ] Set up log aggregation (ship logs from `nexus.access` logger)
- [ ] Add health check endpoint at `/health`

---

## 18. Extension Guide

### Adding a new middleware

```python
# nexus/middleware/auth_header.py
from nexus.middleware.base import BaseMiddleware

class RequireAPIKeyMiddleware(BaseMiddleware):
    def __init__(self, call_next, *, api_key: str):
        super().__init__(call_next)
        self.api_key = api_key

    async def dispatch(self, request, call_next):
        if request.headers.get("x-api-key") != self.api_key:
            from nexus.core.response import JSONResponse
            return JSONResponse({"error": "Invalid API key"}, status_code=401)
        return await call_next(request)

# Register
app.add_middleware(RequireAPIKeyMiddleware, api_key="secret-key")
```

### Adding a new field type

```python
from nexus.orm.fields import Field

class UUIDField(Field):
    db_type = "TEXT"

    def python_to_db(self, value):
        return str(value) if value else None

    def db_to_python(self, value):
        import uuid
        return uuid.UUID(value) if value else None
```

### Adding a new AI provider

```python
from nexus.ai.engine import AIEngine, AIResponse

class MyCustomEngine(AIEngine):
    async def _call_api(self, payload: dict) -> AIResponse:
        # Call your custom API
        result = await my_custom_api_call(payload)
        return AIResponse(content=result["text"], model=self.model)
```

### Adding a new database backend

Replace `AsyncSQLiteConnection` in `ModelManager`:

```python
from nexus.orm.manager import ModelManager

class AsyncPostgresManager(ModelManager):
    def __init__(self, dsn: str):
        self._dsn = dsn
        # Use asyncpg instead of sqlite3
        import asyncpg
        self._pool = None

    async def connect(self):
        import asyncpg
        self._pool = await asyncpg.create_pool(self._dsn)
```

---

## 19. Troubleshooting

### `asyncio.run()` error: "This event loop is already running"

Caused by calling `asyncio.run()` inside an already-running async context.

**Fix:** Use `await` directly, or use `asyncio.ensure_future()`.

### `LookupError: No provider registered for <class>`

The DI container doesn't know about this class.

**Fix:** Call `app.register(MyClass)` or `app.register_instance(MyClass, instance)` before the first request.

### Rate limiter not persisting state between tests

The middleware was being re-instantiated per request.

**Fix:** (Already fixed in this codebase) — Middleware is built once in `_build_handler_chain()` and cached in `self._handler_chain`.

### JWT token expired immediately

Token `expires_in` is in **seconds**, not milliseconds.

```python
auth = JWTAuth(secret="s", expires_in=3600)  # 1 hour, not 3.6 seconds
```

### WebSocket handler not receiving messages

Ensure you call `await ws.accept()` before reading. Without this, the handshake is not complete.

### CI: `ruff` failing but tests pass locally

Different ruff versions may have different rules enabled. Always run `ruff check --fix` before committing.

```bash
.venv/Scripts/ruff check nexus/ tests/ --fix
```

### ORM: `assert self._conn is not None` error

Forgot to call `await db.connect()` before using the database.

**Fix:** Always call in the `on_startup` hook:
```python
@app.on_startup
async def startup():
    await db.connect()
    await db.create_tables(User, Post)
```

---

## Appendix — Quick Reference Card

```
Start app:    uvicorn app:app --reload
Run tests:    pytest tests/ -v
Lint:         ruff check nexus/ tests/ --fix
Type check:   mypy nexus/
New project:  nexus new myproject
List routes:  nexus routes

Key URLs:
  /docs        Swagger UI
  /redoc       ReDoc
  /openapi.json  Raw schema

Module imports:
  from nexus import Nexus, Request, Response
  from nexus.orm import Model, ModelManager, IntField, StrField
  from nexus.auth.jwt import JWTAuth, jwt_required
  from nexus.auth.rbac import RBACPolicy, requires_role
  from nexus.cache.memory import Cache, cached
  from nexus.tasks.queue import TaskQueue, task
  from nexus.websocket.connection import RoomManager
  from nexus.ai.engine import AIEngine
  from nexus.ai.embeddings import EmbeddingEngine
  from nexus.ai.rag import RAGPipeline
  from nexus.middleware import CORSMiddleware, RateLimitMiddleware, LoggingMiddleware
  from nexus.di.dependencies import Depends
```
