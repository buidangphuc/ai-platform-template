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
├── mongo.py          # build_mongo_client (lazy motor import; optional [mongo] extra)
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
├── mongo.py          # Mongo (MONGO_ENABLED, MONGODB_URI, timeouts) — disabled by default
├── ai.py             # LLM router + Langfuse + RAG
├── messaging.py      # Queue, tasks, worker, outbox, webhooks
└── platform.py       # Auth, rate limit, cache, objects, idempotency, quota
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

Backends are `Literal` aliases (e.g. `RateLimitBackend = Literal["memory", "redis"]`), so `Settings` rejects unknown values. Dispatch is an exhaustive `match` with no default branch; pyright (`reportMatchNotExhaustive`) fails until a new value has its `case`.

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
├── __init__.py       # Empty — import from the defining file
├── engine.py         # build_engine, build_sessionmaker, DbSession, get_db, check_postgres_connection
└── model.py          # Base, TimestampMixin, CreatedAtMixin, UpdatedAtMixin, ActorAuditMixin, id_key, utcnow
```

Import each symbol from the file that defines it (ORM models only need `model.py`,
so they don't load the engine or FastAPI):

```python
from app.core.database.engine import DbSession
from app.core.database.model import Base, TimestampMixin, utcnow
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
    check_timeout_seconds: float = 2.0,
)
```

No hardcoded postgres/redis slots. Each opener registers its own readiness
check on `resources.health_checks` (a `HealthChecks` registry) as its resource
comes up, and `build_health_service` hands the registry to `HealthService`:

```python
resources.health_checks.register("redis", partial(check_redis_connection, redis))
```

Checks run concurrently and each is bounded by `HEALTH_CHECK_TIMEOUT_SECONDS`
(a timeout reports `error`). Adding a dependency check (queue, vector DB, model
server) = one `register` call in its opener, no change in `health.py`.

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

Three immutable policies + one stateful object. "Transient" is defined once
(`is_transient_error`: 408, 429, 5xx, timeouts, connection errors) and shared by
retry and the breaker; deterministic 4xx never retries or trips failover.

```python
RetryPolicy(
    max_attempts: int,
    retry_status_codes: tuple[int, ...],
    retry_exceptions: bool,
    retry_on: Callable[[BaseException], bool],  # default is_transient_error
    base_delay_seconds: float,   # capped exponential, full jitter
    max_delay_seconds: float,
    rng: Callable[[], float],    # injectable for tests
)
# Usage
decision = policy.decision(attempt=N, status_code=503, error=None)
# decision.should_retry, decision.next_delay_seconds (honors Retry-After)

CircuitBreakerPolicy(failure_threshold, cooldown_seconds)
breaker = policy.build(clock=...)  # CircuitBreaker: closed -> open -> half-open
breaker.try_acquire() / record_success() / record_failure(error)

TimeoutPolicy(timeout_seconds: float)  # Used by callers with asyncio.wait_for
```

Used by: `messaging/webhooks/dispatcher.py`, `ai/llm/router.py` (per-target circuit breakers for the ordered failover chain), `ai/rag/service.py` (timeout), `ai/evals/runner.py` (timeout), `messaging/outbox/publisher.py`. (Worker retry uses `WORKER_MAX_ATTEMPTS`, not a `RetryPolicy`.)

---

## redis.py

Two functions only:

- `build_redis_client(settings) -> Redis` — single async client with timeout config
- `check_redis_connection(redis) -> None` — ping for health check

The client is owned by `app.state.resources.redis` and shared across cache, rate_limit, queue, task store. (Idempotency is postgres-backed via `PostgresIdempotencyStore`, not Redis.) Don't close it from individual modules — bootstrap closes it on shutdown.

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
RedactionPolicy(*, mode: Literal["off", "redacted", "full"] = "redacted")
policy.redact_text(text)       # "redacted": strip email/bearer/secret patterns
policy.redact_mapping(metadata) # redacts dict values, keeps keys
```

Modes: `"full"` passes text through unchanged, `"redacted"` (default) strips
email/bearer/secret patterns, `"off"` replaces content with `"[redacted]"`
entirely. `RedactionPolicy.from_trace_content(value)` maps an unknown string to
the safe `"redacted"` default.

Used by `app/modules/ai/rag/service.py` before indexing documents (so vector store never contains raw PII).

---

## pagination.py

Generic pagination primitives:

```python
class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

class PaginationMeta(BaseModel):
    limit: int
    offset: int
    total: int = Field(ge=0)

class ListResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    pagination: PaginationMeta
```

The keyword-only helper `build_list_response(*, items, total, params) -> ListResponse[ItemT]` assembles the `PaginationMeta` from `params` and `total`.

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
