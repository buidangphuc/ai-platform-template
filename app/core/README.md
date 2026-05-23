# app/core/

Platform primitives shared across the whole app. Everything here is **vendor-neutral, business-agnostic, no I/O at import time**. Side effects only happen when explicit factories or builders are called.

If something is specific to a single business feature → it belongs in `app/modules/business/`, not here. If it's specific to one infrastructure adapter → it belongs in `app/modules/{platform,messaging,ai}/`.

## Layout

```
core/
├── config/           # Pydantic Settings (mixin package)
├── database/         # Postgres engine + ORM mixins (subpackage)
├── errors.py         # AppError hierarchy + response envelope + validation formatter
├── health.py         # HealthService — generic check registry
├── logging.py        # loguru ↔ stdlib bridge + request_id context injection
├── middleware.py     # 6 ASGI middleware classes
├── pagination.py     # PaginationParams + ListResponse generic
├── redaction.py      # RedactionPolicy for PII / secrets
├── redis.py          # build_redis_client + check_redis_connection
├── request_context.py # RequestIdMiddleware + ContextVar accessor
└── resilience.py     # RetryPolicy, CircuitBreaker, TimeoutPolicy
```

---

## config/

Mixin pattern: one `BaseModel` per concern area, composed into one `Settings` via multiple inheritance. Field access stays **flat** — `settings.POSTGRES_HOST`, not `settings.infra.postgres.host`.

```
config/
├── __init__.py       # Settings composed + get_settings() + production safety + redacted_summary
├── runtime.py        # Environment enum, project metadata, logging, graceful shutdown
├── http.py           # CORS, trusted hosts, body limit, security headers, gzip, request timeout
├── infra.py          # Postgres + Redis
├── ai.py             # LLM router + Langfuse + RAG
├── messaging.py      # Queue, tasks, worker, outbox, webhooks
└── platform.py       # Auth, rate limit, cache, objects, idempotency
```

### Adding a field

Pick the mixin matching the concern. Use Pydantic `Field` for range validation — **don't write `@field_validator` for simple positive / non-negative checks**.

```python
# Good
MAX_REQUEST_BODY_BYTES: int = Field(default=10 * 1024 * 1024, gt=0)
GZIP_COMPRESS_LEVEL: int = Field(default=5, ge=1, le=9)

# Bad — duplicates Field semantics
@field_validator("MAX_REQUEST_BODY_BYTES")
def validate_max_body(cls, v): ...
```

Reserve `@field_validator` and `@model_validator` for cross-field or semantic checks that `Field` can't express (e.g. production safety guards).

### Adding a backend / adapter

**Don't** add `RATE_LIMIT_BACKENDS = {"memory", "redis"}` style allowlists here. The factory (`app/modules/<X>/factory.py`) handles dispatch and raises `ValueError` on unknown. Allowlisting in config layer duplicates work and blocks scaling.

### Adding a new section

1. Create `config/<area>.py` with a `BaseModel` mixin
2. Add it to `Settings` MRO in `config/__init__.py`

The mixin is flat — no nesting.

### Environment enum

`runtime.Environment` is a `StrEnum` with `.is_local` / `.is_production` helpers. The setter normalizes case (`ENVIRONMENT=Prod` → `Environment.PROD`).

```python
if settings.ENVIRONMENT.is_production:
    ...
```

### Production safety (`__init__.py::validate_runtime_safety`)

`@model_validator(mode="after")` runs after all fields are validated. Refuses to start a production environment with:
- `DOCS_ENABLED=True`
- `*` in `CORS_ALLOW_ORIGINS` / `TRUSTED_HOSTS`
- Weak `AUTH_BEARER_TOKEN` (in `WEAK_AUTH_TOKENS` set or shorter than 24 chars)
- Missing `AUTH_BEARER_TOKEN` outside dev/local/test

---

## database/

```
database/
├── __init__.py       # Re-exports — caller imports `from app.core.database import X`
├── engine.py         # build_engine, build_sessionmaker, Base, DbSession, get_db, check_postgres_connection
└── model.py          # TimestampMixin, CreatedAtMixin, UpdatedAtMixin, ActorAuditMixin, id_key, utcnow
```

External callers use one import path:

```python
from app.core.database import (
    Base, DbSession, TimestampMixin, ActorAuditMixin, id_key, utcnow,
)
```

`DbSession = Annotated[AsyncSession, Depends(get_db)]` — drop into FastAPI endpoints.

`get_db` reads `app.state.resources.sessionmaker`; raises 503 `database_not_configured` if missing.

---

## errors.py

| Symbol | Purpose |
|---|---|
| `AppError` | Base — carries `code`, `message`, `status_code`, `data`, optional `headers` |
| `BadRequestError` (400), `UnauthorizedError` (401), `ForbiddenError` (403), `NotFoundError` (404), `MethodNotAllowedError` (405), `ConflictError` (409), `UnprocessableEntityError` (422), `RateLimitError` (429), `ServerError` (500), `ServiceUnavailableError` (503), `TokenError` | Concrete subclasses |
| `_envelope(...)` | `{"error": {"code", "message", "request_id", "data?"}}` |
| `register_exception_handlers(app)` | Wires `AppError`, `RequestValidationError`, `HTTPException` to JSONResponse |
| `format_validation_errors(errors)` | Maps Pydantic error codes (`missing`, `too_long`...) to user-friendly messages |
| `PYDANTIC_ERROR_MESSAGES` | Lookup table for the formatter |

`RateLimitError(retry_after_seconds=N)` automatically sets `Retry-After: N` header via `AppError.headers`.

**Always raise `AppError` subclasses from business code** — never raw `HTTPException`. The handler in `register_exception_handlers` gives consistent envelopes.

---

## health.py

```python
HealthService(
    check_external_dependencies: bool = True,
    checks: tuple[tuple[str, DependencyCheck], ...] = (),
)
```

No hardcoded postgres/redis slots. Bootstrap registers what's enabled:

```python
checks = []
if resources.sessionmaker:
    checks.append(("postgres", partial(check_postgres_connection, resources.sessionmaker)))
if resources.redis:
    checks.append(("redis", partial(check_redis_connection, resources.redis)))
HealthService(checks=tuple(checks))
```

Adding a new dependency check (queue, vector DB, etc.) = append one tuple, no code change in `health.py`.

---

## middleware.py

| Class | Role |
|---|---|
| `AccessLogMiddleware` | Logs method/path/status/duration/principal/request_id |
| `RequestBodyLimitMiddleware` | Reject bodies > `MAX_REQUEST_BODY_BYTES` |
| `SecurityHeadersMiddleware` | HSTS + standard security headers |
| `InFlightTracker` + `InFlightTrackerMiddleware` | Drains in-flight requests during graceful shutdown |
| `RequestTimeoutMiddleware` | Wraps handler in `asyncio.wait_for`. Exclude paths via `REQUEST_TIMEOUT_EXCLUDE_PATTERNS` |
| `IPRateLimitMiddleware` | Per-IP rate limit; reads `app.state.resources.ip_rate_limiter` lazily (works even before lifespan opens limiters) |

Install order is set by `app/bootstrap/middleware.py::install_core_middlewares()`. Middleware that reads from `app.state.resources` uses lazy lookup at request time — middleware is added during `create_app`, resources are built during lifespan.

---

## resilience.py

Three immutable policies + one stateful object:

```python
RetryPolicy(
    max_attempts: int,
    retry_status_codes: tuple[int, ...],
    retry_exceptions: bool,
    backoff_seconds: tuple[float, ...],
)
# Usage
decision = policy.decision(attempt=N, status_code=503, error=None)
# decision.should_retry, decision.next_delay_seconds

CircuitBreakerPolicy(failure_threshold, failure_status_codes, failure_status_range)
breaker = policy.build()  # CircuitBreaker (stateful)
breaker.allows_request() / record_success() / record_failure(status_code=...)

TimeoutPolicy(timeout_seconds: float)  # Used by callers with asyncio.wait_for
```

Used by: `messaging/webhooks/dispatcher.py`, `ai/llm/router.py` (circuit breaker for primary→secondary failover), `ai/rag/service.py` (timeout), `messaging/outbox/publisher.py`, `messaging/tasks/...`.

---

## redis.py

Two functions only:

- `build_redis_client(settings) -> Redis` — single async client with timeout config
- `check_redis_connection(redis) -> None` — ping for health check

The client is owned by `app.state.resources.redis` and shared across cache, rate_limit, idempotency, queue, task store. Don't close it from individual modules — bootstrap closes it on shutdown.

---

## request_context.py

- `RequestIdMiddleware` — generates or accepts `X-Request-ID` header, stores in `request.state.request_id`, emits in response
- `get_request_id()` — ContextVar accessor (works inside background tasks and logger)
- `set_request_id(value)` / `reset_request_id(token)` — for tests / manual control

The request_id flows through:
1. Response header `X-Request-ID`
2. Access log line
3. Error envelope (`{"error": {"request_id": ...}}`)
4. Audit log records
5. Langfuse trace metadata

---

## logging.py

`configure_logging(level, json_mode, enqueue)` — sets up loguru handler, intercepts stdlib `logging` (`InterceptHandler`), and injects `request_id` into every record via context binding.

`LOG_JSON=true` switches loguru output to JSON for production log aggregators.

`LOG_ENQUEUE=true` puts logging on a background queue (avoids blocking event loop on slow handlers).

---

## redaction.py

```python
RedactionPolicy(mode: Literal["redacted", "raw"])
policy.redact_text(text)       # strips email/bearer/secret patterns
policy.redact_mapping(metadata) # redacts dict values, keeps keys
```

Used by `app/modules/ai/rag/service.py` before indexing documents (so vector store never contains raw PII).

---

## pagination.py

Generic pagination primitives:

```python
class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

class PaginationMeta(BaseModel): ...

class ListResponse(BaseModel, Generic[T]):
    items: list[T]
    meta: PaginationMeta
```

Not yet wired into any endpoint. Template scaffold — use when adding `/list` style endpoints.

---

## What does NOT belong here

- ❌ Anything that imports `app.modules.*` at top level (creates circular dependency)
- ❌ Module-specific helpers (cache TTL math, rate limit window calc, etc.) — those live in the module's own files
- ❌ Business validation rules (price > 0, status transitions) — those belong in `app/modules/business/`
- ❌ HTTP route definitions — those belong in `app/api/v1/`
- ❌ Vendor SDK direct usage (boto3, langchain) — wrap behind a module's Protocol

If you're tempted to add one of these, consider:
- A new `app/modules/<group>/<thing>/` instead
- Or `app/bootstrap/` if it's about application wiring
