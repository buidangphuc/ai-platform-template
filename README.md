# AI Solution Engineering Platform

Reusable FastAPI foundation for AI solution engineering work. The template keeps the app shell, security baseline, and local data services clean so project-specific AI product code can be added without inheriting old business coupling.

## Scope

This repository currently covers the local application foundation:

- Import-safe FastAPI app factory.
- Pydantic settings and `.env` workflow.
- Health/readiness endpoints.
- Request ID middleware, logging context, and standard error envelope.
- Static Bearer token authentication.
- Lean product primitives: service context, explicit DB transactions,
  pagination schemas, audit events, and idempotency persistence.
- Fixed-window rate limiting foundation.
- Native LangChain chat model wiring with per-instance Langfuse tracker.
- LlamaIndex advanced retrieval support code using native `Document` and
  `NodeWithScore` primitives, retrieval smoke checks, and redaction policy.
- Self-hosted Langfuse local stack via Docker Compose for tracing, prompt
  management, and eval scores.
- PostgreSQL model metadata with Alembic.
- Local Docker build/run path.

Deployment pipelines are intentionally out of scope. Each team or client environment can bring its own deployment platform.

## Requirements

- Python 3.12+
- uv
- Docker and Docker Compose for local container checks

## Quickstart

```bash
cp .env.example .env
uv sync --dev
make test
make dev
```

The API starts on `http://localhost:8000`.

Useful endpoints:

- `GET /healthz` — liveness probe (always 200 while process is alive)
- `GET /readyz` — readiness probe (503 when Postgres/Redis are unreachable)
- `GET /api/v1/auth/me`
- `POST /api/v1/completions`
- `POST /api/v1/completions/stream`

All `/api/v1/*` platform endpoints except health checks require
`Authorization: Bearer <AUTH_BEARER_TOKEN>`.

The completions endpoints are intentionally thin transport skeletons. They
accept chat messages, call an injected `CompletionHandler`, and return either
one JSON completion or server-sent stream deltas. They do not know prompt
templates, model selection, caching, retrieval, or product workflow logic.

## Docker

```bash
cp .env.example .env
make docker-build
make docker-run
```

The Docker path is a local golden path only. It builds the API image and runs the API, PostgreSQL, and Redis with `docker-compose.local.yaml`.

To run the API with a local self-hosted Langfuse stack for AI tracing, prompt
management, and eval scores:

```bash
cp .env.example .env
make docker-run-langfuse
```

Langfuse is available at `http://localhost:3000`. The local project and API
keys are bootstrapped from `.env` through Langfuse headless initialization. The
API container uses `LANGFUSE_DOCKER_BASE_URL=http://langfuse-web:3000`; host
Python processes can use `LANGFUSE_BASE_URL=http://localhost:3000`.

## Project Layout

```text
app/
  api/                  Versioned FastAPI routers
  bootstrap/            App factory and service wiring
  core/                 Settings, database, Redis, errors, logging, health
  modules/
    identity/           Static Bearer principal and auth dependency
    audit/              Product audit events for actor/resource/action history
    idempotency/        Concrete idempotency-key persistence helpers
    llm/                LangChain chat model factory and per-instance Langfuse tracker
    rag/                LlamaIndex-backed knowledge retrieval and tool builders
    rate_limit/         Rate limit service contracts and implementations
alembic/                Migration environment
scripts/                Local helper scripts (including Langfuse smoke runners)
tests/                  Unit and integration tests
```

## Local Commands

```bash
make dev                    # run local API with uvicorn reload
make test                   # run full pytest suite
make smoke-langfuse         # exercise the Langfuse callback against the local stack
make smoke-langfuse-prompt  # exercise the Langfuse prompt-management flow
make hygiene                # check stale template coupling
```

## Secrets

Copy `.env.example` to `.env` for local development. Keep real secrets in environment variables or your team's secret manager, not in Git.

## Runtime Defaults

The template boots without cloud credentials. The app factory does not create AI
runtime services by default; project business logic can wire LangChain or
LlamaIndex services where it actually needs them.

- `CHAT_MODEL=`
- `AUTH_BEARER_TOKEN=change-me-local-bearer-token`
- `AUTH_SUBJECT=local-user`
- `AUTH_ROLES=admin`
- `IDEMPOTENCY_ENABLED=false`
- `CORS_ALLOW_ORIGINS=*`
- `TRUSTED_HOSTS=*`
- `MAX_REQUEST_BODY_BYTES=10485760`
- `LANGFUSE_ENABLED=true`
- `LANGFUSE_PUBLIC_KEY=lf_pk_local_ai_platform`
- `LANGFUSE_SECRET_KEY=lf_sk_local_ai_platform`
- `LANGFUSE_BASE_URL=http://localhost:3000`

To use a real model, install the relevant LangChain provider package, set the
provider's standard environment variables in your runtime, then set
`CHAT_MODEL` to a native LangChain target such as `openai:gpt-4.1-mini` or
`anthropic:claude-sonnet-4-5`. Knowledge retrieval integrations should pass
LlamaIndex `Document` objects into `KnowledgeRetrievalService` and consume
retrieved `NodeWithScore` values instead of adding template-owned RAG schemas,
rerankers, or vector-store adapters.

HTTP middleware provides CORS, trusted-host enforcement, a request body limit,
standard error envelopes for FastAPI/Starlette HTTP errors, and access logs with
method, path, status, duration, request id, and authenticated principal when
available.

Business endpoints should depend on `app.core.context.ServiceContextDep` when
they need the request boundary. The context is intentionally small:
`request_id`, authenticated `principal`, optional `idempotency_key`, and DB
session. `idempotency_key` is only parsed when `IDEMPOTENCY_ENABLED=true`; with
the default `false`, incoming `Idempotency-Key` headers are ignored. The context
does not carry Redis, object storage clients, feature flags, or AI runtimes; add
those directly at the business module boundary when a project actually needs
them.

Endpoint wiring should stay local to the owning module. API routers should keep
only HTTP concerns: path/query/body parsing, response models or envelopes, and a
small call into a business service. Runtime wiring belongs in a module-local
provider such as `app/modules/business/<domain>/providers.py`; that provider
may read `app.state` resources and settings, then construct the service and its
runtime dependencies. Business services should receive explicit constructor
dependencies and must not read FastAPI `Request`, `app.state`, or a global
service locator. Avoid central API-level `deps.py` files that accumulate
feature-specific wiring.

Database access uses a session-per-request dependency. The dependency rolls
back on unhandled exceptions and always closes the session, but it does not
auto-commit. Business services own explicit `commit()` calls.

List endpoints can reuse `app.core.pagination.PaginationParams` and
`build_list_response(...)` for offset-based responses:
`{"items": [...], "pagination": {"limit": 50, "offset": 0, "total": 123}}`.
The template intentionally does not ship a generic query builder.

`app.modules.audit.record_audit_event(...)` records product audit events for
"who did what to which resource". Audit metadata is guarded against raw prompt,
message, payload, input, output, and generated text keys; store IDs, counts,
status, duration, error codes, and `langfuse_trace_id` instead. Langfuse remains
the place for AI trace details.

When `IDEMPOTENCY_ENABLED=true`,
`app.core.idempotency.get_idempotency_key` validates the optional
`Idempotency-Key` header. `app.modules.idempotency` adds concrete persistence
with an `idempotency_keys` table. Request hashes include method, path, body, and
principal id. Reusing the same key with a different request returns
`409 idempotency_key_conflict`; reusing an in-progress key returns
`409 idempotency_key_in_progress`. Streaming responses are intentionally outside
this contract.

App observability, experiment tracking, LLM response caching, object storage,
and job queues are intentionally not wrapped by template adapters in this phase.
Use the tools required by the target project directly at the module boundary.
Database access goes through `app.core.database.DbSession`, a normal SQLAlchemy
session dependency.

Langfuse is only wired at the AI execution boundary. Use
`build_llm_instance(..., instance_id="...", service_name="...")` from
`app.modules.llm.runtime` to create a native LangChain `BaseChatModel` plus a
per-instance Langfuse tracker. Pass `instance.trace_config(...)` into LangChain
calls to keep parallel LLM services separated by instance, service, session,
user, and request metadata.

To use the completions transport, inject business logic at app construction:

```python
from collections.abc import AsyncIterator

from app.api.v1.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from app.bootstrap.application import create_app


class MyCompletionHandler:
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return CompletionResult(content="...")

    async def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[CompletionStreamChunk]:
        yield CompletionStreamChunk(delta="...")


app = create_app(MyCompletionHandler())
```

Without an injected handler, `/api/v1/completions` and
`/api/v1/completions/stream` return `501 completion_handler_not_configured`.

The app factory registers a FastAPI lifespan that calls
`langfuse.get_client().flush()` on shutdown when `LANGFUSE_ENABLED=true` and
`init_resources=True`, so any buffered traces from per-instance trackers are
drained before the process exits. The app factory also owns shared runtime
resources on `app.state.engine`, `app.state.sessionmaker`, and
`app.state.redis`; readiness checks and DB dependencies reuse those handles,
and the lifespan closes Redis plus disposes the SQLAlchemy engine on shutdown.
Tests construct the app with `init_resources=False`, which skips external
readiness checks.

## Bearer Auth

Set `AUTH_BEARER_TOKEN` in `.env`, then call protected endpoints with:

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $AUTH_BEARER_TOKEN"
```

The template intentionally does not create users, passwords, sessions, or API
key tables. `AUTH_SUBJECT` and `AUTH_ROLES` define the local principal returned
by `/api/v1/auth/me` as `{"id": "...", "type": "service", "scopes": [...]}`.
