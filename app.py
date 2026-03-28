"""
Nexus Framework — demo/example application.

Run with:
    uvicorn app:app --reload

Explore at:
    http://localhost:8000/docs   (Swagger UI)
    http://localhost:8000/redoc  (ReDoc)
"""

from nexus import Nexus, Request, Response
from nexus.auth.jwt import JWTAuth
from nexus.cache.memory import Cache, cached
from nexus.di.dependencies import Depends
from nexus.middleware import CORSMiddleware, LoggingMiddleware, RateLimitMiddleware
from nexus.orm import ModelManager, Model, IntField, StrField, BoolField, DateTimeField
from nexus.tasks.queue import TaskQueue

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = Nexus(
    title="Nexus Demo API",
    version="1.0.0",
    description="Demonstrating the full Nexus framework feature set.",
    debug=True,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_window=100, window_seconds=60)

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

db = ModelManager("sqlite:///demo.db")
cache = Cache(default_ttl=300)
task_queue = TaskQueue(workers=2)
auth = JWTAuth(secret="nexus-demo-secret", expires_in=3600)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Model):
    __table__ = "users"
    id = IntField(primary_key=True)
    name = StrField(max_length=128, nullable=False)
    email = StrField(unique=True, nullable=False)
    role = StrField(default="user")
    is_active = BoolField(default=True)
    created_at = DateTimeField(auto_now_add=True)


class Post(Model):
    __table__ = "posts"
    id = IntField(primary_key=True)
    title = StrField(nullable=False)
    content = StrField()
    author_id = IntField()
    published = BoolField(default=False)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------

@app.on_startup
async def startup():
    await db.connect()
    await db.create_tables(User, Post)
    await task_queue.start()
    print("✅ Nexus demo app started")


@app.on_shutdown
async def shutdown():
    await db.close()
    await task_queue.stop()
    print("🛑 Nexus demo app stopped")


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def send_welcome_email(user_id: int, email: str) -> None:
    print(f"[Task] Sending welcome email to {email}")


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------

def get_auth():
    return auth


def get_db():
    return db


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", tags=["meta"], summary="Root health check")
async def index(request: Request) -> Response:
    return Response.json({
        "status": "ok",
        "framework": "Nexus",
        "version": "0.1.0",
        "docs": "/docs",
    })


@app.get("/health", tags=["meta"])
async def health(request: Request) -> Response:
    return Response.json({"status": "healthy"})


# -- Auth --

@app.post("/auth/login", tags=["auth"], summary="Login and get JWT token")
async def login(request: Request) -> Response:
    body = await request.json()
    if not body or "email" not in body:
        return Response.json({"error": "email required"}, status_code=400)

    # Demo: accept any email
    token = auth.create({"sub": body["email"], "role": body.get("role", "user")})
    return Response.json({"access_token": token, "token_type": "Bearer"})


# -- Users --

@app.get("/users", tags=["users"], summary="List all users")
@cached(cache, ttl=60)
async def list_users(request: Request) -> Response:
    users = await db.query(User).filter(is_active=True).order_by("created_at").all()
    return Response.json({"users": [u.to_dict() for u in users]})


@app.post("/users", tags=["users"], summary="Create a user")
async def create_user(request: Request) -> Response:
    body = await request.json()
    if not body or not body.get("name") or not body.get("email"):
        return Response.json({"error": "name and email are required"}, status_code=400)

    try:
        user = await db.create(User, name=body["name"], email=body["email"])
    except Exception as exc:
        return Response.json({"error": str(exc)}, status_code=409)

    await task_queue.enqueue(send_welcome_email, user.id, user.email)
    return Response.json(user.to_dict(), status_code=201)


@app.get("/users/{id}", tags=["users"], summary="Get a user by ID")
async def get_user(request: Request, id: int) -> Response:
    user = await db.get(User, id)
    if not user:
        return Response.json({"error": "User not found"}, status_code=404)
    return Response.json(user.to_dict())


@app.delete("/users/{id}", tags=["users"], summary="Delete a user")
async def delete_user(request: Request, id: int) -> Response:
    user = await db.get(User, id)
    if not user:
        return Response.json({"error": "User not found"}, status_code=404)
    await db.delete(user)
    return Response.no_content()


# -- Posts --

@app.get("/posts", tags=["posts"])
async def list_posts(request: Request) -> Response:
    published_only = request.query("published") == "true"
    qb = db.query(Post)
    if published_only:
        qb = qb.filter(published=True)
    posts = await qb.order_by("created_at", desc=True).all()
    return Response.json({"posts": [p.to_dict() for p in posts]})


@app.post("/posts", tags=["posts"])
async def create_post(request: Request) -> Response:
    body = await request.json()
    post = await db.create(
        Post,
        title=body.get("title", "Untitled"),
        content=body.get("content", ""),
        author_id=body.get("author_id", 0),
    )
    return Response.json(post.to_dict(), status_code=201)


# -- Tasks --

@app.get("/tasks/stats", tags=["tasks"])
async def task_stats(request: Request) -> Response:
    return Response.json(task_queue.stats())


# -- Cache --

@app.delete("/cache/clear", tags=["cache"])
async def clear_cache(request: Request) -> Response:
    cache.clear()
    return Response.json({"cleared": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
