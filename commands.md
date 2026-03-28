# Nexus Framework — Command Reference

## The Short Answer

Instead of:
```bash
uvicorn app:app --reload
```

Use the **project-native CLI**:
```bash
nexus run
```

Both commands start the same server. `nexus run` is the Nexus-idiomatic way — it wraps uvicorn internally and adds project-aware defaults.

---

## Why `nexus run` Works

`pyproject.toml` registers a console script entry point:

```toml
[project.scripts]
nexus = "nexus.cli.main:main"
```

When you run `pip install -e .` (editable install), pip writes a `nexus` executable into your virtual environment's `Scripts/` (Windows) or `bin/` (Unix) folder. That executable calls `nexus.cli.main:main` directly.

Internally `cmd_run()` builds and delegates to uvicorn:

```python
cmd = [sys.executable, "-m", "uvicorn", app_path, "--host", host, "--port", port]
if reload:
    cmd.append("--reload")
subprocess.run(cmd, check=True)
```

So `nexus run` **is** uvicorn — just invoked through the project's own CLI.

---

## `nexus run` — Full Reference

### Basic usage

```bash
nexus run
```

Starts the server at `http://127.0.0.1:8000` with auto-reload enabled.
API docs available at `http://127.0.0.1:8000/docs`.

### Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--app` | `str` | `app:app` | ASGI app location (`module:variable`) |
| `--host` | `str` | `127.0.0.1` | Network interface to bind |
| `--port` | `int` | `8000` | TCP port to listen on |
| `--no-reload` | flag | off | Disable auto-reload on file changes |
| `--workers` | `int` | — | Number of worker processes (disables reload) |

### Examples

```bash
# Default — localhost:8000 with reload
nexus run

# Custom host/port
nexus run --host 0.0.0.0 --port 9000

# Different app module
nexus run --app myapp.server:application

# Production mode — no reload, 4 workers
nexus run --no-reload --workers 4 --host 0.0.0.0

# Expose to local network (accessible from other devices)
nexus run --host 0.0.0.0
```

---

## All Nexus CLI Commands

### `nexus run` — Start the development server

```bash
nexus run [--app APP] [--host HOST] [--port PORT] [--no-reload] [--workers N]
```

Wraps uvicorn with project-aware defaults. Prints startup URLs to the terminal.

---

### `nexus new <name>` — Scaffold a new project

```bash
nexus new myproject
nexus new myproject --directory /path/to/parent
```

Generates a complete project structure:

```
myproject/
├── myproject/
│   ├── __init__.py
│   ├── config.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── user.py
│   ├── routes/
│   │   ├── __init__.py
│   │   └── api.py
│   └── services/
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   └── test_app.py
├── app.py
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── .env.example
├── .gitignore
├── Dockerfile
└── docker-compose.yml
```

After scaffolding:
```bash
cd myproject
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
nexus run
```

---

### `nexus routes` — List registered routes

```bash
nexus routes
nexus routes --app app:app
```

Prints a table of all routes registered on the app:

```
METHOD     PATH                                     NAME                           TAGS
------------------------------------------------------------------------------------------
GET        /                                        index
GET        /health                                  health
POST       /auth/login                              login                          auth
GET        /users                                   list_users                     users
POST       /users                                   create_user                    users
GET        /users/{id}                              get_user                       users
...
```

---

## Side-by-Side Comparison

| Goal | Old command | New command |
|------|-------------|-------------|
| Start dev server | `uvicorn app:app --reload` | `nexus run` |
| Custom port | `uvicorn app:app --reload --port 9000` | `nexus run --port 9000` |
| Bind all interfaces | `uvicorn app:app --reload --host 0.0.0.0` | `nexus run --host 0.0.0.0` |
| Production (4 workers) | `uvicorn app:app --host 0.0.0.0 --workers 4` | `nexus run --host 0.0.0.0 --no-reload --workers 4` |
| Different app variable | `uvicorn mymod:create_app --reload` | `nexus run --app mymod:create_app` |
| View routes | *(no equivalent)* | `nexus routes` |
| Scaffold project | *(no equivalent)* | `nexus new myproject` |

---

## Using `python -m nexus` (Alternative)

If the `nexus` script is not on your PATH (e.g., venv not activated), use the module form:

```bash
python -m nexus run
python -m nexus run --port 9000
python -m nexus routes
python -m nexus new myproject
```

This works as long as the package is installed or on `PYTHONPATH`.

---

## Direct uvicorn (Still Valid)

`uvicorn app:app --reload` still works perfectly — `nexus run` is just a convenience wrapper around it. Use raw uvicorn when you need flags that the Nexus CLI doesn't expose:

```bash
# SSL/TLS
uvicorn app:app --ssl-keyfile key.pem --ssl-certfile cert.pem

# Custom log level
uvicorn app:app --reload --log-level debug

# Unix socket instead of TCP port
uvicorn app:app --uds /tmp/nexus.sock

# HTTP/2 (requires hypercorn instead)
hypercorn app:app --bind 0.0.0.0:8000
```

---

## Environment Variables

Both `nexus run` and `uvicorn` respect these environment variables from `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///app.db` | ORM connection string |
| `JWT_SECRET` | `change-me-in-production` | JWT signing secret |
| `DEBUG` | `true` | Enables debug mode and verbose errors |

Load `.env` before starting:
```bash
# Windows
set /p < .env && nexus run

# Mac/Linux (with python-dotenv installed)
nexus run   # app.py can load dotenv itself
```

---

## Quick Reference Card

```
nexus run                          → http://127.0.0.1:8000  (reload on)
nexus run --port 9000              → http://127.0.0.1:9000  (reload on)
nexus run --host 0.0.0.0           → http://0.0.0.0:8000    (all interfaces)
nexus run --no-reload              → production-safe, no file watching
nexus run --workers 4 --no-reload  → multi-process production mode
nexus routes                       → list all API routes
nexus new <name>                   → scaffold new project
python -m nexus run                → same as nexus run (no PATH needed)
```
