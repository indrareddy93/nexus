"""
Nexus CLI — project scaffolding, dev server runner.

Commands:
    nexus new <name>          Create a new Nexus project
    nexus run [--host] [--port] [--reload]  Start the dev server
    nexus routes              List all registered routes
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# ------------------------------------------------------------------
# Templates
# ------------------------------------------------------------------

_PROJECT_STRUCTURE = {
    "{name}/__init__.py": "",
    "{name}/routes/__init__.py": "",
    "{name}/routes/api.py": '''\
"""API routes."""
from nexus import Nexus, Request, Response

router_v1 = None  # Will be used in app.py

''',
    "{name}/models/__init__.py": "",
    "{name}/models/user.py": '''\
"""User model."""
from nexus.orm import Model, IntField, StrField, BoolField, DateTimeField


class User(Model):
    __table__ = "users"

    id = IntField(primary_key=True)
    name = StrField(max_length=128, nullable=False)
    email = StrField(unique=True, nullable=False)
    is_active = BoolField(default=True)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
''',
    "{name}/services/__init__.py": "",
    "{name}/config.py": '''\
"""Application configuration."""
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///app.db")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
''',
    "app.py": '''\
"""
{name} — Nexus application entry point.

Run with:
    uvicorn app:app --reload
"""
from nexus import Nexus, Request, Response
from nexus.middleware import CORSMiddleware, LoggingMiddleware
from nexus.orm import ModelManager

from {name}.config import DATABASE_URL, DEBUG, JWT_SECRET
from {name}.models.user import User

app = Nexus(
    title="{name} API",
    version="1.0.0",
    description="Built with Nexus Framework",
    debug=DEBUG,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(LoggingMiddleware)

# Database
db = ModelManager(DATABASE_URL)


@app.on_startup
async def startup() -> None:
    await db.connect()
    await db.create_tables(User)


@app.on_shutdown
async def shutdown() -> None:
    await db.close()


# Routes
@app.get("/")
async def index(request: Request) -> Response:
    """Health check."""
    return Response.json({"status": "ok", "framework": "Nexus"})


@app.get("/health")
async def health(request: Request) -> Response:
    """Liveness probe."""
    return Response.json({"status": "healthy"})
''',
    "requirements.txt": '''\
nexus-framework
uvicorn[standard]>=0.30.0
httpx>=0.27.0
''',
    "requirements-dev.txt": '''\
pytest>=8.0
pytest-asyncio>=0.23
ruff>=0.5.0
mypy>=1.10
''',
    ".env.example": '''\
DATABASE_URL=sqlite:///app.db
JWT_SECRET=change-me-in-production
DEBUG=true
''',
    ".gitignore": '''\
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/
.env
*.db
*.sqlite3
.mypy_cache/
.ruff_cache/
.pytest_cache/
''',
    "Dockerfile": '''\
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
''',
    "docker-compose.yml": '''\
version: "3.9"

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///app.db
      - JWT_SECRET=change-me-in-production
      - DEBUG=false
    volumes:
      - .:/app
''',
    "pyproject.toml": '''\
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"
''',
    "tests/__init__.py": "",
    "tests/test_app.py": '''\
"""Basic smoke tests for {name}."""
import pytest
from app import app


@pytest.mark.asyncio
async def test_index():
    """Test the root endpoint returns 200."""
    from nexus.testing import TestClient
    client = TestClient(app)
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
''',
}


# ------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------

def cmd_new(args: argparse.Namespace) -> None:
    """Create a new Nexus project."""
    name = args.name
    target = Path(args.directory or ".") / name

    if target.exists():
        print(f"❌  Directory {target} already exists.")
        sys.exit(1)

    print(f"🚀  Creating Nexus project: {name}")
    target.mkdir(parents=True)

    for path_template, content_template in _PROJECT_STRUCTURE.items():
        path = target / path_template.format(name=name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content_template.format(name=name))
        print(f"   ✓  {path.relative_to(target)}")

    print(f"\n✅  Project {name!r} created at {target.resolve()}")
    print("\nNext steps:\n")
    print(f"   cd {target}")
    print("   python -m venv .venv && source .venv/bin/activate  # (or .venv\\Scripts\\activate on Windows)")
    print("   pip install -r requirements.txt")
    print("   uvicorn app:app --reload")
    print("\nAPI docs will be available at http://localhost:8000/docs\n")


def cmd_run(args: argparse.Namespace) -> None:
    """Start the Nexus development server using uvicorn."""
    host = args.host or "127.0.0.1"
    port = str(args.port or 8000)
    app_path = args.app or "app:app"
    reload = not args.no_reload

    cmd = [
        sys.executable, "-m", "uvicorn",
        app_path,
        "--host", host,
        "--port", port,
    ]
    if reload:
        cmd.append("--reload")
    if args.workers:
        cmd.extend(["--workers", str(args.workers)])

    print(f"🚀  Starting Nexus dev server → http://{host}:{port}")
    print(f"   Docs: http://{host}:{port}/docs\n")
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n🛑  Server stopped.")
    except FileNotFoundError:
        print("❌  uvicorn not found. Install it: pip install uvicorn[standard]")
        sys.exit(1)


def cmd_routes(args: argparse.Namespace) -> None:
    """Print all registered routes."""
    import importlib
    app_module, _, app_attr = (args.app or "app:app").partition(":")
    try:
        mod = importlib.import_module(app_module)
        app = getattr(mod, app_attr or "app")
    except Exception as exc:
        print(f"❌  Could not import {args.app!r}: {exc}")
        sys.exit(1)

    routes = getattr(app, "routes", [])
    if not routes:
        print("No routes registered.")
        return

    print(f"\n{'METHOD':<10} {'PATH':<40} {'NAME':<30} {'TAGS'}")
    print("-" * 90)
    for r in routes:
        methods = ",".join(sorted(r.methods))
        tags = ",".join(r.tags) if r.tags else ""
        print(f"{methods:<10} {r.path:<40} {(r.name or ''):<30} {tags}")
    print()


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="nexus",
        description="Nexus Framework CLI",
    )
    sub = parser.add_subparsers(dest="command")

    # nexus new <name>
    p_new = sub.add_parser("new", help="Create a new Nexus project")
    p_new.add_argument("name", help="Project name")
    p_new.add_argument("--directory", "-d", help="Parent directory (default: current dir)")

    # nexus run
    p_run = sub.add_parser("run", help="Start the development server")
    p_run.add_argument("--app", default="app:app", help="ASGI app location (default: app:app)")
    p_run.add_argument("--host", default="127.0.0.1", help="Bind host")
    p_run.add_argument("--port", type=int, default=8000, help="Bind port")
    p_run.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    p_run.add_argument("--workers", type=int, help="Number of worker processes")

    # nexus routes
    p_routes = sub.add_parser("routes", help="List registered routes")
    p_routes.add_argument("--app", default="app:app")

    args = parser.parse_args()

    if args.command == "new":
        cmd_new(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "routes":
        cmd_routes(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
