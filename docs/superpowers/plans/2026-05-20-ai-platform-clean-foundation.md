# AI Platform Clean Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the repository into an import-safe FastAPI foundation for the AI platform template, with clean config, health checks, API key auth, rate limiting, feedback capture, and Docker-local golden path.

**Architecture:** This is Plan 1 of the platform rebuild. It removes stale business coupling and creates the stable application foundation that later plans will extend with adapters, RAG, agents, LLMOps, and MLOps. Keep the implementation concrete in the app foundation; use contracts/adapters only where this phase needs an integration boundary.

**Tech Stack:** FastAPI, Pydantic Settings, SQLAlchemy async, Alembic, Redis asyncio, pytest, httpx ASGI transport, Docker Compose, Make.

---

## Scope Boundary

This plan implements only Phase 1 from the design spec:

- Clean app bootstrap.
- Settings and secret workflow.
- Health/readiness.
- Request ID, error envelope, and logging baseline.
- API key auth.
- Redis-backed rate limit with in-memory test path.
- Feedback capture endpoint and schema.
- PostgreSQL/Alembic cleanup.
- Docker/Make golden path.
- Template hygiene checks.

The following are intentionally separate plans:

- Contracts and default adapters.
- RAG and LLM runtime capabilities.
- Agent runtime support.
- Research/MLOps workspace.
- Full docs and recipes.

## File Map

Create:

- `app/api/__init__.py` - API package marker.
- `app/api/router.py` - root API router.
- `app/api/v1/__init__.py` - v1 package marker.
- `app/api/v1/auth/__init__.py` - auth API package marker.
- `app/api/v1/auth/router.py` - API key management endpoints.
- `app/api/v1/feedback/__init__.py` - feedback API package marker.
- `app/api/v1/feedback/router.py` - feedback capture endpoint.
- `app/api/v1/health/__init__.py` - health API package marker.
- `app/api/v1/health/router.py` - health/readiness endpoints.
- `app/bootstrap/__init__.py` - bootstrap package marker.
- `app/bootstrap/application.py` - FastAPI app factory.
- `app/core/config.py` - settings and environment parsing.
- `app/core/database.py` - async SQLAlchemy engine/session setup.
- `app/core/errors.py` - application error type and exception handlers.
- `app/core/health.py` - dependency health check service.
- `app/core/logging.py` - logging setup.
- `app/core/redis.py` - Redis client factory.
- `app/core/request_context.py` - request ID context helpers.
- `app/core/security.py` - secret hashing and API key generation helpers.
- `app/modules/__init__.py` - modules package marker.
- `app/modules/feedback/__init__.py` - feedback module marker.
- `app/modules/feedback/models.py` - feedback database model.
- `app/modules/feedback/repository.py` - feedback persistence.
- `app/modules/feedback/schemas.py` - feedback request/response schemas.
- `app/modules/identity/__init__.py` - identity module marker.
- `app/modules/identity/auth.py` - API key authentication dependency.
- `app/modules/identity/models.py` - API key/user database models.
- `app/modules/identity/repository.py` - API key persistence.
- `app/modules/identity/schemas.py` - API key request/response schemas.
- `app/modules/rate_limit/__init__.py` - rate limit module marker.
- `app/modules/rate_limit/service.py` - Redis-backed fixed-window rate limit.
- `tests/conftest.py` - shared test fixtures.
- `tests/unit/core/test_config.py` - settings tests.
- `tests/unit/core/test_error_envelope.py` - error response tests.
- `tests/unit/core/test_logging.py` - logging context tests.
- `tests/unit/core/test_security.py` - API key hashing tests.
- `tests/unit/modules/test_rate_limit.py` - rate limit tests.
- `tests/integration/test_health.py` - health/readiness API tests.
- `tests/integration/test_auth.py` - API key auth API tests.
- `tests/integration/test_feedback.py` - feedback API tests.
- `scripts/check_template_hygiene.sh` - stale coupling check.
- `Makefile` - golden path commands.

Modify:

- `main.py` - import app from new app factory.
- `pyproject.toml` - add test dependencies and pytest config.
- `requirements.txt` - add runtime dependencies used by Docker.
- `.env.example` - safe example values for all required settings.
- `README.md` - quickstart and secret workflow.
- `alembic/env.py` - use PostgreSQL settings and `app` models.
- `docker-compose.local.yaml` - local Postgres/Redis/API stack.
- `Dockerfile` - build clean app with current dependency source.

Delete or replace stale files during the hygiene task:

- `app/router.py`
- `common/security/jwt.py`
- `middleware/jwt_auth_middleware.py`
- `middleware/opera_log_middleware.py`
- `common/socketio/server.py`
- `scripts/celery-start.sh`
- old Alembic versions that reference removed business tables.

## Task 1: Settings and Secret Workflow

**Files:**

- Create: `app/core/config.py`
- Create: `tests/unit/core/test_config.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add test dependencies**

Edit `pyproject.toml` so the main dependencies include:

```toml
asyncpg = ">=0.30.0,<0.31.0"
redis = ">=5.2.1,<6.0.0"
```

Edit `pyproject.toml` so the dev dependency group contains these packages:

```toml
[tool.poetry.group.dev.dependencies]
ruff = "^0.11.2"
pyink = "^24.10.1"
isort = "^6.0.1"
pre-commit = "^4.3.0"
detect-secrets = "^1.5.0"
pytest = "^8.3.5"
pytest-asyncio = "^0.25.3"
httpx = "^0.28.1"
```

Add this pytest configuration:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]
```

Edit `requirements.txt` so it contains these runtime packages:

```text
asyncpg
redis
```

- [ ] **Step 2: Write the failing settings tests**

Create `tests/unit/core/test_config.py`:

```python
from app.core.config import Settings


def test_settings_defaults_are_local_safe():
    settings = Settings(
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="",  # pragma: allowlist secret
        REDIS_DATABASE=0,
        API_KEY_PEPPER="test-pepper",  # pragma: allowlist secret
    )

    assert settings.PROJECT_NAME == "AI Solution Engineering Platform"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.POSTGRES_URL.startswith("postgresql+asyncpg://")
    assert settings.TRACE_CONTENT == "redacted"


def test_settings_redacts_secret_values():
    settings = Settings(
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="redis-secret",  # pragma: allowlist secret
        REDIS_DATABASE=0,
        API_KEY_PEPPER="pepper-secret",  # pragma: allowlist secret
        OPENAI_API_KEY="sk-test",  # pragma: allowlist secret
    )

    summary = settings.redacted_summary()

    assert summary["REDIS_PASSWORD"] == "***"
    assert summary["API_KEY_PEPPER"] == "***"
    assert summary["OPENAI_API_KEY"] == "***"
    assert summary["ENVIRONMENT"] == "test"
```

- [ ] **Step 3: Run the settings tests and verify they fail**

Run:

```bash
poetry run pytest tests/unit/core/test_config.py -v
```

Expected: fail because `app.core.config` does not exist.

- [ ] **Step 4: Implement settings**

Create `app/core/config.py`:

```python
from functools import lru_cache
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: str = "dev"
    PROJECT_NAME: str = "AI Solution Engineering Platform"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Reusable FastAPI foundation for AI solution engineering"
    API_V1_PREFIX: str = "/api/v1"

    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DATABASE: int = 0
    REDIS_TIMEOUT_SECONDS: int = 5

    API_KEY_PEPPER: str
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 60

    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    TRACE_CONTENT: Literal["off", "redacted", "full"] = "redacted"

    OPENAI_API_KEY: str = ""
    LLM_PROVIDER: str = "fake"
    EMBEDDING_PROVIDER: str = "fake"
    VECTOR_STORE: str = "in_memory"
    STORAGE_BACKEND: str = "local"
    JOB_BACKEND: str = "in_process"

    @computed_field
    @property
    def POSTGRES_URL(self) -> str:
        return (
            "postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def redacted_summary(self) -> dict[str, object]:
        values = self.model_dump(mode="json")
        secret_names = {
            "POSTGRES_PASSWORD",
            "REDIS_PASSWORD",
            "API_KEY_PEPPER",
            "OPENAI_API_KEY",
        }
        return {
            key: "***" if key in secret_names and values.get(key) else value
            for key, value in values.items()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Update `.env.example`**

Replace `.env.example` with:

```dotenv
ENVIRONMENT=dev
PROJECT_NAME="AI Solution Engineering Platform"
VERSION=0.1.0
DESCRIPTION="Reusable FastAPI foundation for AI solution engineering"
API_V1_PREFIX=/api/v1

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres # pragma: allowlist secret
POSTGRES_DB=ai_platform

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD= # pragma: allowlist secret
REDIS_DATABASE=0
REDIS_TIMEOUT_SECONDS=5

API_KEY_PEPPER=change-me-local-dev-only # pragma: allowlist secret
DEFAULT_RATE_LIMIT_PER_MINUTE=60

OTEL_EXPORTER_OTLP_ENDPOINT=
TRACE_CONTENT=redacted

OPENAI_API_KEY= # pragma: allowlist secret
LLM_PROVIDER=fake
EMBEDDING_PROVIDER=fake
VECTOR_STORE=in_memory
STORAGE_BACKEND=local
JOB_BACKEND=in_process
```

- [ ] **Step 6: Add README secret guidance**

Add this section to `README.md`:

```markdown
## Secrets

Copy `.env.example` to `.env` for local development. Keep real secrets in environment variables or your team's secret manager, not in Git. The template does not include Vault, cloud secret manager, or organization-specific secret workflows by default.
```

- [ ] **Step 7: Run settings tests and verify they pass**

Run:

```bash
poetry run pytest tests/unit/core/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml requirements.txt .env.example README.md app/core/config.py tests/unit/core/test_config.py
git commit -m "feat: add clean settings foundation"
```

## Task 2: Import-Safe FastAPI App and Health Endpoints

**Files:**

- Create: `app/bootstrap/application.py`
- Create: `app/api/__init__.py`
- Create: `app/api/router.py`
- Create: `app/api/v1/__init__.py`
- Create: `app/api/v1/health/__init__.py`
- Create: `app/api/v1/health/router.py`
- Create: `app/core/health.py`
- Create: `tests/conftest.py`
- Create: `tests/integration/test_health.py`
- Modify: `main.py`

- [ ] **Step 1: Write the failing app and health tests**

Create `tests/conftest.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings


@pytest.fixture()
def test_settings() -> Settings:
    return Settings(
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="",  # pragma: allowlist secret
        REDIS_DATABASE=0,
        API_KEY_PEPPER="test-pepper",  # pragma: allowlist secret
    )


@pytest.fixture()
async def client(test_settings: Settings):
    app = create_app(settings=test_settings, init_resources=False)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client
```

Create `tests/integration/test_health.py`:

```python
async def test_health_returns_api_status(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_returns_dependency_statuses(client):
    response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["api"] == "ok"
```

- [ ] **Step 2: Run the health tests and verify they fail**

Run:

```bash
poetry run pytest tests/integration/test_health.py -v
```

Expected: fail because `app.bootstrap.application` does not exist.

- [ ] **Step 3: Implement app factory and health router**

Create empty package markers:

```bash
touch app/api/__init__.py app/api/v1/__init__.py app/api/v1/health/__init__.py app/bootstrap/__init__.py
```

Create `app/core/health.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class HealthResult:
    status: str
    dependencies: dict[str, str]


class HealthService:
    def __init__(self, check_external_dependencies: bool = True) -> None:
        self.check_external_dependencies = check_external_dependencies

    async def health(self) -> HealthResult:
        return HealthResult(status="ok", dependencies={"api": "ok"})

    async def readiness(self) -> HealthResult:
        dependencies = {"api": "ok"}
        return HealthResult(status="ok", dependencies=dependencies)
```

Create `app/api/v1/health/router.py`:

```python
from fastapi import APIRouter, Request

from app.core.health import HealthService

router = APIRouter(tags=["health"])


def _health_service(request: Request) -> HealthService:
    return request.app.state.health_service


@router.get("/health")
async def health(request: Request):
    result = await _health_service(request).health()
    return {"status": result.status}


@router.get("/ready")
async def readiness(request: Request):
    result = await _health_service(request).readiness()
    return {
        "status": result.status,
        "dependencies": result.dependencies,
    }
```

Create `app/api/router.py`:

```python
from fastapi import APIRouter

from app.api.v1.health.router import router as health_router
from app.core.config import Settings


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)
    return router
```

Create `app/bootstrap/application.py`:

```python
from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.health import HealthService


def create_app(
    settings: Settings | None = None,
    *,
    init_resources: bool = True,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title=resolved_settings.PROJECT_NAME,
        version=resolved_settings.VERSION,
        description=resolved_settings.DESCRIPTION,
    )
    app.state.settings = resolved_settings
    app.state.health_service = HealthService(
        check_external_dependencies=init_resources,
    )
    app.include_router(build_api_router(resolved_settings))
    return app
```

Replace `main.py` with:

```python
from app.bootstrap.application import create_app

app = create_app()
```

- [ ] **Step 4: Run the health tests and verify they pass**

Run:

```bash
poetry run pytest tests/integration/test_health.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add main.py app/api app/bootstrap app/core/health.py tests/conftest.py tests/integration/test_health.py
git commit -m "feat: add clean FastAPI app factory"
```

## Task 3: Error Envelope and Request ID

**Files:**

- Create: `app/core/errors.py`
- Create: `app/core/request_context.py`
- Create: `tests/unit/core/test_error_envelope.py`
- Create: `app/core/logging.py`
- Create: `tests/unit/core/test_logging.py`
- Modify: `app/bootstrap/application.py`

- [ ] **Step 1: Write failing error envelope test**

Create `tests/unit/core/test_error_envelope.py`:

```python
from fastapi import APIRouter

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.core.errors import AppError


def _settings() -> Settings:
    return Settings(
        ENVIRONMENT="test",
        POSTGRES_HOST="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="postgres",  # pragma: allowlist secret
        POSTGRES_DB="ai_platform",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_PASSWORD="",  # pragma: allowlist secret
        REDIS_DATABASE=0,
        API_KEY_PEPPER="test-pepper",  # pragma: allowlist secret
    )


async def test_app_error_uses_standard_envelope():
    router = APIRouter()

    @router.get("/boom")
    async def boom():
        raise AppError(code="test_error", message="Test error", status_code=418)

    app = create_app(settings=_settings(), init_resources=False)
    app.include_router(router)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/boom", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 418
    assert response.json() == {
        "error": {
            "code": "test_error",
            "message": "Test error",
            "request_id": "req-test",
        }
    }
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
poetry run pytest tests/unit/core/test_error_envelope.py -v
```

Expected: fail because `app.core.errors.AppError` does not exist.

- [ ] **Step 3: Add logging context test**

Create `tests/unit/core/test_logging.py`:

```python
import logging

from app.core.logging import RequestIdFilter
from app.core.request_context import set_request_id


def test_request_id_filter_adds_request_id():
    set_request_id("req-log")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )

    RequestIdFilter().filter(record)

    assert record.request_id == "req-log"
```

- [ ] **Step 4: Implement request context, logging, and exception handler**

Create `app/core/request_context.py`:

```python
from contextvars import ContextVar
from uuid import uuid4

from starlette.types import ASGIApp, Receive, Scope, Send

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> None:
    _request_id.set(value)


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        raw_request_id = headers.get(self.header_name.lower().encode())
        request_id = raw_request_id.decode() if raw_request_id else f"req_{uuid4().hex}"
        set_request_id(request_id)

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((self.header_name.encode(), request_id.encode()))
            await send(message)

        await self.app(scope, receive, send_with_request_id)
```

Create `app/core/errors.py`:

```python
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.request_context import get_request_id


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": get_request_id(),
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
```

Create `app/core/logging.py`:

```python
import logging

from app.core.request_context import get_request_id


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [req=%(request_id)s] %(name)s - %(message)s",
    )
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(RequestIdFilter())
```

Modify `app/bootstrap/application.py`:

```python
from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.health import HealthService
from app.core.logging import configure_logging
from app.core.request_context import RequestIdMiddleware


def create_app(
    settings: Settings | None = None,
    *,
    init_resources: bool = True,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging()
    app = FastAPI(
        title=resolved_settings.PROJECT_NAME,
        version=resolved_settings.VERSION,
        description=resolved_settings.DESCRIPTION,
    )
    app.state.settings = resolved_settings
    app.state.health_service = HealthService(
        check_external_dependencies=init_resources,
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(build_api_router(resolved_settings))
    return app
```

- [ ] **Step 5: Run the error envelope, logging, and health tests**

Run:

```bash
poetry run pytest tests/unit/core/test_error_envelope.py tests/unit/core/test_logging.py tests/integration/test_health.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/core/errors.py app/core/logging.py app/core/request_context.py app/bootstrap/application.py tests/unit/core/test_error_envelope.py tests/unit/core/test_logging.py
git commit -m "feat: add request id and error envelope"
```

## Task 4: API Key Security Helpers

**Files:**

- Create: `app/core/security.py`
- Create: `tests/unit/core/test_security.py`

- [ ] **Step 1: Write failing security tests**

Create `tests/unit/core/test_security.py`:

```python
from app.core.security import create_api_key, hash_api_key, verify_api_key


def test_create_api_key_returns_prefix_and_secret():
    api_key = create_api_key(prefix="ak_test")

    assert api_key.startswith("ak_test_")
    assert len(api_key) > len("ak_test_")


def test_hash_and_verify_api_key():
    api_key = "ak_test_example"  # pragma: allowlist secret
    digest = hash_api_key(api_key, pepper="pepper")

    assert digest != api_key
    assert verify_api_key(api_key, digest, pepper="pepper")
    assert not verify_api_key("ak_test_other", digest, pepper="pepper")
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
poetry run pytest tests/unit/core/test_security.py -v
```

Expected: fail because `app.core.security` does not exist.

- [ ] **Step 3: Implement security helpers**

Create `app/core/security.py`:

```python
import hashlib
import hmac
import secrets


def create_api_key(prefix: str = "ak") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str, *, pepper: str) -> str:
    payload = f"{pepper}:{api_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_api_key(api_key: str, digest: str, *, pepper: str) -> bool:
    candidate = hash_api_key(api_key, pepper=pepper)
    return hmac.compare_digest(candidate, digest)
```

- [ ] **Step 4: Run security tests**

Run:

```bash
poetry run pytest tests/unit/core/test_security.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/core/security.py tests/unit/core/test_security.py
git commit -m "feat: add API key security helpers"
```

## Task 5: Database, Identity Models, and API Key Auth

**Files:**

- Create: `app/core/database.py`
- Create: `app/modules/identity/models.py`
- Create: `app/modules/identity/repository.py`
- Create: `app/modules/identity/schemas.py`
- Create: `app/modules/identity/auth.py`
- Create: `app/api/v1/auth/router.py`
- Create: `tests/integration/test_auth.py`
- Modify: `app/api/router.py`
- Modify: `app/bootstrap/application.py`

- [ ] **Step 1: Write failing auth API tests**

Create package markers:

```bash
mkdir -p app/modules/identity app/api/v1/auth tests/integration
touch app/modules/__init__.py app/modules/identity/__init__.py app/api/v1/auth/__init__.py
```

Create `tests/integration/test_auth.py`:

```python
async def test_create_api_key_returns_secret_once(client):
    response = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "local-test"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "local-test"
    assert body["api_key"].startswith("ak_")
    assert body["api_key_id"]


async def test_authenticated_endpoint_accepts_api_key(client):
    created = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "local-test"},
    )
    api_key = created.json()["api_key"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 200
    assert response.json()["auth_type"] == "api_key"
```

- [ ] **Step 2: Run auth tests and verify they fail**

Run:

```bash
poetry run pytest tests/integration/test_auth.py -v
```

Expected: fail because the auth router does not exist.

- [ ] **Step 3: Implement database module**

Create `app/core/database.py`:

```python
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings, get_settings


class Base(AsyncAttrs, DeclarativeBase):
    pass


def build_sessionmaker(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings.POSTGRES_URL, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    settings = get_settings()
    sessionmaker = build_sessionmaker(settings)
    async with sessionmaker() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
```

- [ ] **Step 4: Implement identity schemas and repository**

Create `app/modules/identity/models.py`:

```python
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"key_{uuid4().hex}")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Create `app/modules/identity/schemas.py`:

```python
from pydantic import BaseModel, Field


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CreateApiKeyResponse(BaseModel):
    api_key_id: str
    name: str
    api_key: str


class AuthenticatedPrincipal(BaseModel):
    auth_type: str
    api_key_id: str
    name: str
```

Create `app/modules/identity/repository.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import ApiKey


class ApiKeyRepository:
    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
        self._memory: dict[str, ApiKey] = {}

    async def create(self, *, name: str, key_hash: str) -> ApiKey:
        api_key = ApiKey(name=name, key_hash=key_hash)
        if self.db is None:
            self._memory[api_key.id] = api_key
            return api_key
        self.db.add(api_key)
        await self.db.flush()
        return api_key

    async def get_active_by_hash(self, key_hash: str) -> ApiKey | None:
        if self.db is None:
            return next(
                (item for item in self._memory.values() if item.key_hash == key_hash and item.is_active),
                None,
            )
        result = await self.db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        )
        return result.scalar_one_or_none()
```

- [ ] **Step 5: Implement auth dependency and router**

Create `app/modules/identity/auth.py`:

```python
from fastapi import Header

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_api_key
from app.modules.identity.repository import ApiKeyRepository
from app.modules.identity.schemas import AuthenticatedPrincipal


async def authenticate_api_key(
    authorization: str | None,
    *,
    settings: Settings,
    repository: ApiKeyRepository,
) -> AuthenticatedPrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(code="unauthorized", message="Missing API key", status_code=401)

    raw_api_key = authorization.removeprefix("Bearer ").strip()
    key_hash = hash_api_key(raw_api_key, pepper=settings.API_KEY_PEPPER)
    api_key = await repository.get_active_by_hash(key_hash)
    if api_key is None:
        raise AppError(code="unauthorized", message="Invalid API key", status_code=401)

    return AuthenticatedPrincipal(
        auth_type="api_key",
        api_key_id=api_key.id,
        name=api_key.name,
    )


def authorization_header(authorization: str | None = Header(default=None, alias="Authorization")) -> str | None:
    return authorization
```

Create `app/api/v1/auth/router.py`:

```python
from fastapi import APIRouter, Request, Response, status

from app.core.security import create_api_key, hash_api_key
from app.modules.identity.auth import authenticate_api_key
from app.modules.identity.repository import ApiKeyRepository
from app.modules.identity.schemas import (
    AuthenticatedPrincipal,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _repository(request: Request) -> ApiKeyRepository:
    return request.app.state.api_key_repository


@router.post("/api-keys", response_model=CreateApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_key(payload: CreateApiKeyRequest, request: Request, response: Response):
    settings = request.app.state.settings
    raw_key = create_api_key()
    key_hash = hash_api_key(raw_key, pepper=settings.API_KEY_PEPPER)
    api_key = await _repository(request).create(name=payload.name, key_hash=key_hash)
    response.headers["Cache-Control"] = "no-store"
    return CreateApiKeyResponse(api_key_id=api_key.id, name=api_key.name, api_key=raw_key)


@router.get("/me", response_model=AuthenticatedPrincipal)
async def me(request: Request):
    principal = await authenticate_api_key(
        request.headers.get("Authorization"),
        settings=request.app.state.settings,
        repository=_repository(request),
    )
    return principal
```

Modify `app/api/router.py`:

```python
from fastapi import APIRouter

from app.api.v1.auth.router import router as auth_router
from app.api.v1.health.router import router as health_router
from app.core.config import Settings


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    router.include_router(health_router)
    router.include_router(auth_router)
    return router
```

Modify `app/bootstrap/application.py` to initialize in-memory repository for test and local bootstrap:

```python
from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.health import HealthService
from app.core.request_context import RequestIdMiddleware
from app.modules.identity.repository import ApiKeyRepository


def create_app(
    settings: Settings | None = None,
    *,
    init_resources: bool = True,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title=resolved_settings.PROJECT_NAME,
        version=resolved_settings.VERSION,
        description=resolved_settings.DESCRIPTION,
    )
    app.state.settings = resolved_settings
    app.state.health_service = HealthService(
        check_external_dependencies=init_resources,
    )
    app.state.api_key_repository = ApiKeyRepository()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(build_api_router(resolved_settings))
    return app
```

- [ ] **Step 6: Run auth and existing tests**

Run:

```bash
poetry run pytest tests/unit/core tests/integration/test_health.py tests/integration/test_auth.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/core/database.py app/modules app/api/v1/auth app/api/router.py app/bootstrap/application.py tests/integration/test_auth.py
git commit -m "feat: add API key identity foundation"
```

## Task 6: Rate Limit Foundation

**Files:**

- Create: `app/modules/rate_limit/service.py`
- Create: `app/core/redis.py`
- Create: `tests/unit/modules/test_rate_limit.py`
- Modify: `app/bootstrap/application.py`
- Modify: `app/api/v1/auth/router.py`

- [ ] **Step 1: Write failing rate limit tests**

Create package marker:

```bash
mkdir -p app/modules/rate_limit tests/unit/modules
touch app/modules/rate_limit/__init__.py
```

Create `tests/unit/modules/test_rate_limit.py`:

```python
from app.modules.rate_limit.service import InMemoryRateLimiter, RedisRateLimiter


async def test_in_memory_rate_limiter_allows_until_limit():
    limiter = InMemoryRateLimiter(limit=2)

    first = await limiter.check("api-key-1")
    second = await limiter.check("api-key-1")
    third = await limiter.check("api-key-1")

    assert first.allowed
    assert second.allowed
    assert not third.allowed
    assert third.remaining == 0


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds


async def test_redis_rate_limiter_sets_window_on_first_hit():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis=redis, limit=2, window_seconds=60)

    result = await limiter.check("api-key-1")

    assert result.allowed
    assert result.remaining == 1
    assert redis.expirations["rate-limit:api-key-1"] == 60
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
poetry run pytest tests/unit/modules/test_rate_limit.py -v
```

Expected: fail because `app.modules.rate_limit.service` does not exist.

- [ ] **Step 3: Implement in-memory rate limiter**

Create `app/modules/rate_limit/service.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int


class InMemoryRateLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._counts: dict[str, int] = {}

    async def check(self, key: str) -> RateLimitResult:
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        remaining = max(self.limit - count, 0)
        return RateLimitResult(allowed=count <= self.limit, remaining=remaining)


class RedisRateLimiter:
    def __init__(self, *, redis, limit: int, window_seconds: int = 60) -> None:
        self.redis = redis
        self.limit = limit
        self.window_seconds = window_seconds

    async def check(self, key: str) -> RateLimitResult:
        redis_key = f"rate-limit:{key}"
        count = await self.redis.incr(redis_key)
        if count == 1:
            await self.redis.expire(redis_key, self.window_seconds)
        remaining = max(self.limit - count, 0)
        return RateLimitResult(allowed=count <= self.limit, remaining=remaining)
```

Create `app/core/redis.py`:

```python
from redis.asyncio import Redis

from app.core.config import Settings


def build_redis_client(settings: Settings) -> Redis:
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        db=settings.REDIS_DATABASE,
        socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
        decode_responses=True,
    )
```

- [ ] **Step 4: Wire rate limiter into `/auth/me`**

Modify `app/bootstrap/application.py` to add:

```python
from app.modules.rate_limit.service import InMemoryRateLimiter
```

and set state before registering routes:

```python
app.state.rate_limiter = InMemoryRateLimiter(
    limit=resolved_settings.DEFAULT_RATE_LIMIT_PER_MINUTE,
)
```

Modify `app/api/v1/auth/router.py` inside `me` after `principal` is resolved:

```python
    rate_limit = await request.app.state.rate_limiter.check(principal.api_key_id)
    if not rate_limit.allowed:
        from app.core.errors import AppError

        raise AppError(code="rate_limit_exceeded", message="Rate limit exceeded", status_code=429)
```

- [ ] **Step 5: Run rate limit and auth tests**

Run:

```bash
poetry run pytest tests/unit/modules/test_rate_limit.py tests/integration/test_auth.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/core/redis.py app/modules/rate_limit app/bootstrap/application.py app/api/v1/auth/router.py tests/unit/modules/test_rate_limit.py
git commit -m "feat: add rate limit foundation"
```

## Task 7: Feedback Capture Schema and Endpoint

**Files:**

- Create: `app/modules/feedback/models.py`
- Create: `app/modules/feedback/repository.py`
- Create: `app/modules/feedback/schemas.py`
- Create: `app/api/v1/feedback/router.py`
- Create: `tests/integration/test_feedback.py`
- Modify: `app/api/router.py`
- Modify: `app/bootstrap/application.py`

- [ ] **Step 1: Write failing feedback API test**

Create package markers:

```bash
mkdir -p app/modules/feedback app/api/v1/feedback
touch app/modules/feedback/__init__.py app/api/v1/feedback/__init__.py
```

Create `tests/integration/test_feedback.py`:

```python
async def test_capture_feedback(client):
    response = await client.post(
        "/api/v1/feedback",
        json={
            "request_id": "req_1",
            "trace_id": "trace_1",
            "target_type": "llm_response",
            "target_id": "resp_1",
            "rating": "negative",
            "labels": ["hallucination"],
            "comment": "Answer cited the wrong source",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["feedback_id"].startswith("fb_")
    assert body["target_type"] == "llm_response"
    assert body["rating"] == "negative"
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
poetry run pytest tests/integration/test_feedback.py -v
```

Expected: fail because feedback route does not exist.

- [ ] **Step 3: Implement feedback schemas and repository**

Create `app/modules/feedback/schemas.py`:

```python
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

FeedbackTargetType = Literal["llm_response", "rag_answer", "agent_run", "eval_run"]
FeedbackRating = Literal["positive", "negative", "neutral"]


class CreateFeedbackRequest(BaseModel):
    request_id: str
    trace_id: str
    target_type: FeedbackTargetType
    target_id: str
    rating: FeedbackRating
    labels: list[str] = Field(default_factory=list)
    comment: str | None = None


class FeedbackRecord(BaseModel):
    feedback_id: str
    request_id: str
    trace_id: str
    target_type: FeedbackTargetType
    target_id: str
    rating: FeedbackRating
    labels: list[str]
    comment: str | None


def new_feedback_id() -> str:
    return f"fb_{uuid4().hex}"
```

Create `app/modules/feedback/repository.py`:

```python
from app.modules.feedback.schemas import CreateFeedbackRequest, FeedbackRecord, new_feedback_id


class FeedbackRepository:
    def __init__(self) -> None:
        self._items: dict[str, FeedbackRecord] = {}

    async def create(self, payload: CreateFeedbackRequest) -> FeedbackRecord:
        record = FeedbackRecord(
            feedback_id=new_feedback_id(),
            **payload.model_dump(),
        )
        self._items[record.feedback_id] = record
        return record
```

Create `app/modules/feedback/models.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    rating: Mapped[str] = mapped_column(String(32), nullable=False)
    labels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 4: Implement feedback router and wire it**

Create `app/api/v1/feedback/router.py`:

```python
from fastapi import APIRouter, Request, status

from app.modules.feedback.schemas import CreateFeedbackRequest, FeedbackRecord

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackRecord, status_code=status.HTTP_201_CREATED)
async def capture_feedback(payload: CreateFeedbackRequest, request: Request):
    return await request.app.state.feedback_repository.create(payload)
```

Modify `app/api/router.py` to include:

```python
from app.api.v1.feedback.router import router as feedback_router
```

and inside `build_api_router`:

```python
router.include_router(feedback_router)
```

Modify `app/bootstrap/application.py` to import and set:

```python
from app.modules.feedback.repository import FeedbackRepository
```

```python
app.state.feedback_repository = FeedbackRepository()
```

- [ ] **Step 5: Run feedback and health tests**

Run:

```bash
poetry run pytest tests/integration/test_feedback.py tests/integration/test_health.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/feedback app/api/v1/feedback app/api/router.py app/bootstrap/application.py tests/integration/test_feedback.py
git commit -m "feat: add feedback capture endpoint"
```

## Task 8: Alembic PostgreSQL Cleanup

**Files:**

- Modify: `alembic/env.py`
- Delete: old files under `alembic/versions/` that reference removed business tables.

- [ ] **Step 1: Replace Alembic environment**

Replace `alembic/env.py` with:

```python
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings
from app.core.database import Base
from app.modules.feedback.models import Feedback
from app.modules.identity.models import ApiKey

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", settings.POSTGRES_URL.replace("+asyncpg", ""))


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 2: Remove stale Alembic versions**

Run:

```bash
git rm alembic/versions/35b207b54337_add_platform_column_to_feedback.py
```

Expected: file removed from the index. If the file is already absent, run `git status --short alembic/versions` and confirm no old migration remains.

- [ ] **Step 3: Verify Alembic imports**

Run:

```bash
poetry run python -m compileall alembic app
```

Expected: command exits 0.

- [ ] **Step 4: Commit**

```bash
git add alembic/env.py alembic/versions app
git commit -m "feat: clean PostgreSQL migration foundation"
```

## Task 9: Docker, Compose, and Make Golden Path

**Files:**

- Modify: `Dockerfile`
- Modify: `docker-compose.local.yaml`
- Create: `Makefile`

- [ ] **Step 1: Replace Dockerfile**

Replace `Dockerfile` with:

```dockerfile
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip -i https://pypi.org/simple \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Replace local Compose**

Replace `docker-compose.local.yaml` with:

```yaml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    env_file:
      - .env
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    networks:
      - ai-platform

  postgres:
    image: postgres:16
    env_file:
      - .env
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - ai-platform

  redis:
    image: redis:7
    ports:
      - "${REDIS_PORT:-6379}:6379"
    volumes:
      - redis-data:/data
    networks:
      - ai-platform

networks:
  ai-platform:
    driver: bridge

volumes:
  postgres-data:
  redis-data:
```

- [ ] **Step 3: Add Makefile**

Create `Makefile`:

```makefile
.PHONY: dev test eval-smoke docker-build docker-run hygiene

dev:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	poetry run pytest -v

eval-smoke:
	poetry run pytest tests/integration/test_feedback.py -v

docker-build:
	docker build -t ai-platform-template:local .

docker-run:
	docker compose -f docker-compose.local.yaml up

hygiene:
	./scripts/check_template_hygiene.sh
```

- [ ] **Step 4: Run local test command**

Run:

```bash
poetry run pytest tests/unit/core tests/unit/modules tests/integration -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.local.yaml Makefile
git commit -m "feat: add Docker local golden path"
```

## Task 10: Template Hygiene Cleanup

**Files:**

- Create: `scripts/check_template_hygiene.sh`
- Delete: stale business-coupled files listed in the File Map.
- Modify: `README.md`

- [ ] **Step 1: Create hygiene script**

Create `scripts/check_template_hygiene.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

blocked_patterns=(
  "app.admin"
  "app.task"
  "MYSQL_URL"
  "fba_"
  "OperaLog"
)

for pattern in "${blocked_patterns[@]}"; do
  if rg "$pattern" app common core database middleware scripts alembic docker-compose.local.yaml Dockerfile README.md; then
    echo "Blocked stale template pattern found: $pattern" >&2
    exit 1
  fi
done

echo "Template hygiene check passed"
```

Run:

```bash
chmod +x scripts/check_template_hygiene.sh
```

- [ ] **Step 2: Run hygiene check and verify it fails before cleanup**

Run:

```bash
./scripts/check_template_hygiene.sh
```

Expected: fail if stale references remain.

- [ ] **Step 3: Remove stale business-coupled files**

Run:

```bash
git rm app/router.py
git rm common/security/jwt.py
git rm middleware/jwt_auth_middleware.py
git rm middleware/opera_log_middleware.py
git rm common/socketio/server.py
git rm scripts/celery-start.sh
```

If a file is already absent, skip only that exact `git rm` command and continue.

- [ ] **Step 4: Update README quickstart**

Add this section to `README.md`:

````markdown
## Quickstart

```bash
cp .env.example .env
poetry install
make test
make dev
```

For Docker:

```bash
cp .env.example .env
make docker-build
make docker-run
```

The default local path uses safe local services and fake AI providers. Cloud providers and observability backends are added through later adapter profiles.
````

- [ ] **Step 5: Run hygiene and full tests**

Run:

```bash
./scripts/check_template_hygiene.sh
poetry run pytest -v
```

Expected: hygiene check passes and all tests pass.

- [ ] **Step 6: Commit**

```bash
git add README.md scripts/check_template_hygiene.sh
git add -u
git commit -m "chore: remove stale business template coupling"
```

## Task 11: Final Verification

**Files:**

- Verify all files touched in previous tasks.

- [ ] **Step 1: Run formatting and hygiene checks**

Run:

```bash
poetry run ruff check .
./scripts/check_template_hygiene.sh
```

Expected: both commands exit 0.

- [ ] **Step 2: Run test suite**

Run:

```bash
poetry run pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Run Docker build**

Run:

```bash
make docker-build
```

Expected: image `ai-platform-template:local` builds successfully.

- [ ] **Step 4: Confirm worktree only has intentional changes**

Run:

```bash
git status --short
```

Expected: no unstaged implementation changes from this plan.

## Self-Review Checklist

- Spec coverage: This plan covers Phase 1 clean foundation, settings, secrets, health, request ID, errors, API key auth, rate limit, feedback schema, PostgreSQL migration cleanup, Docker local path, and hygiene checks.
- Out of scope by design: adapter contracts, LLM response cache contract, RAG implementation, agent runtime, research workspace, observability profiles, MLflow, DVC, Phoenix, Datadog, and LangGraph.
- Type consistency: app settings are `app.core.config.Settings`; app factory is `app.bootstrap.application.create_app`; auth principal is `AuthenticatedPrincipal`; feedback response is `FeedbackRecord`.
- Execution model: Execute tasks in order. Commit after each task. Do not start Task 2 until Task 1 tests pass.
