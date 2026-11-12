# Usage

How to run, configure and operate this template. For an overview of the repo see the [README](../README.md); for building a product on it see the [template guide](template-guide.md).

## Requirements

- Python >=3.12,<3.14
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
- `GET /readyz` — readiness probe (503 when an enabled dependency — Postgres,
  Redis, or Mongo, gated by `DATABASE_ENABLED`/`REDIS_ENABLED`/`MONGO_ENABLED`
  — is unreachable; with the minimal-core defaults no dependency checks are
  registered, so it always reports ok)
- `POST /api/v1/completions`
- `POST /api/v1/completions/stream`

All `/api/v1/*` platform endpoints except health checks require
`Authorization: Bearer <api-key>` (see [Bearer Auth](#bearer-auth)).

The completions endpoints are intentionally thin transport skeletons. They
accept chat messages, call an injected `CompletionHandler`, and return either
one JSON completion or server-sent stream deltas. They do not know prompt
templates, model selection, caching, retrieval, or product workflow logic.

### Streaming (`POST /api/v1/completions/stream`)

The response is `text/event-stream` with `Cache-Control: no-cache` and
`X-Accel-Buffering: no`. Frames:

- `data: {"type":"content.delta","delta":"...","metadata":{}}` for each piece of text.
- `: ping` comment lines every `SSE_HEARTBEAT_SECONDS` while the model is quiet
  (clients ignore them).
- `data: {"type":"done", ...}` last, with `usage`, `finish_reason` and `model` when
  the handler reported them (plain `{"type":"done"}` otherwise).
- `event: error` + `data: {"type":"error","code":"..."}` if the stream fails after it
  started (codes: `stream_timeout`, `stream_error`, or an application error code);
  the stream then closes with no `done`. The frame never carries exception text.

Failures before the first chunk (guardrail violation, handler startup error, no chunk
within `STREAM_FIRST_TOKEN_TIMEOUT_SECONDS`) return the normal JSON error envelope
(422 / 500 / 504 `stream_timeout`) instead of a `200` stream. A gap longer than
`STREAM_IDLE_TIMEOUT_SECONDS` between chunks ends the stream with `stream_timeout`.
Handlers yield `CompletionStreamChunk`; the last chunk may set `usage` and
`finish_reason`.

With `LLM_ENABLED=true` each LLM call (API and worker, sync or stream) logs one
`completion mode=... outcome=... model=... duration_ms=... ttft_ms=... finish_reason=... input_tokens=...`
line (no content). The default echo handler makes no LLM call and logs no such line.

## Docker

```bash
cp .env.example .env
make docker-build
make docker-run
```

The Docker path is a local golden path only. It builds the image `ai-platform-template:local` and runs, with `ops/compose/local.yaml`, a one-shot `migrate` service (`alembic upgrade head`), then the API and a worker once it completes, plus PostgreSQL and Redis, with database, redis, queue and tasks enabled. Migrations run automatically; there is no manual `make migrate` step. The API is published on `127.0.0.1:8000` only (`API_PORT` changes the port, not the interface).

To run the API with a local self-hosted Langfuse stack for AI tracing, prompt
management, and eval scores:

```bash
cp .env.example .env
cp ops/compose/langfuse.env.example .env.langfuse   # optional Langfuse overrides
make docker-run-langfuse
```

The Langfuse overlay is `ops/compose/langfuse.yaml`; `make docker-run-langfuse` layers it on `ops/compose/local.yaml` and loads `.env.langfuse` when present. The overlay builds the image with the `ai` extra (`UV_EXTRAS=ai`) for the API, the worker and `migrate`, and sets `LANGFUSE_ENABLED`, the Langfuse keys and the in-network base URL for the API. A trace is produced only when the stack also runs with `LLM_ENABLED=true` and a non-empty `CHAT_MODEL` (plus that model's provider key) in `.env`; with `LLM_ENABLED=false` the echo handler makes no LLM call and nothing is traced.

Langfuse is available at `http://localhost:3000`. The local project and API
keys are bootstrapped from `.env` through Langfuse headless initialization. The
API container uses `LANGFUSE_DOCKER_BASE_URL=http://langfuse-web:3000`; host
Python processes can use `LANGFUSE_BASE_URL=http://localhost:3000`.

### Graceful shutdown and Kubernetes

The image runs `python -m app.serve` (also usable locally; `SERVER_HOST` /
`SERVER_PORT`, default `0.0.0.0:8000`). uvicorn closes its listener as soon as it
gets SIGTERM, which would hide the `/readyz` 503 from load balancers, so on the
first SIGTERM/SIGINT `app.serve` marks the app draining (`/readyz` returns 503,
`/healthz` stays 200), keeps accepting for `SHUTDOWN_READINESS_DELAY_SECONDS`
(default 5, `0` disables), then runs the normal graceful shutdown. A second signal
forces exit.

- A `preStop: sleep` hook is optional with this delay; set the delay at least
  `periodSeconds * failureThreshold` of the readiness probe plus endpoint
  propagation time.
- `terminationGracePeriodSeconds` must exceed `SHUTDOWN_READINESS_DELAY_SECONDS` +
  `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS` (connection drain), plus another
  `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS` in the worst case (the lifespan then waits
  for in-flight requests): `5 + 2 * 30 + margin` with the defaults.
## Local commands

Run `make help` for every target. The main ones:

```bash
make dev                    # run local API with uvicorn reload
make test                   # pytest -m "not infra" (what CI runs)
make test-infra             # every test on localinfra, 80% coverage gate
make smoke-langfuse         # exercise the Langfuse callback against the local stack
make smoke-langfuse-prompt  # exercise the Langfuse prompt-management flow
make check-env              # verify .env.example matches Settings fields
make ci                     # ruff checks + env check + typecheck + tests
```

## Secrets

Copy `.env.example` to `.env` for local development. Keep real secrets in environment variables or your team's secret manager, not in Git.

## Local `.env` defaults (from `.env.example`)

The template boots without cloud credentials. The app factory does not create AI
runtime services by default; project business logic can wire LangChain or
LlamaIndex services where it actually needs them.

The values below are what `.env.example` ships for the local golden path — they
are **not** the code defaults. In code every capability `*_ENABLED` flag
defaults to `false` (`LANGFUSE_ENABLED` included, `app/core/config/ai.py`),
`AUTH_API_KEYS` defaults to `""` (no keys, no implicit admin), and `LANGFUSE_BASE_URL` defaults to
`https://cloud.langfuse.com`. Capability backends default to real services (queue `redis`, task store `postgres`, rate limit and cache `redis`, objects `s3`, quota `postgres`, RAG `pgvector`); there is no in-memory backend, so enabling a capability also needs its service. `.env.example` pre-enables Langfuse with dummy
local keys only so `make docker-run-langfuse` works out of the box.

- `CHAT_MODEL=`
- `AUTH_API_KEYS=local-user:admin:<sha256 of change-me-local-bearer-token>`
- `MONGO_ENABLED=false`
- `IDEMPOTENCY_ENABLED=false`
- `CORS_ALLOW_ORIGINS=*`
- `TRUSTED_HOSTS=*`
- `MAX_REQUEST_BODY_BYTES=10485760`
- `LANGFUSE_ENABLED=true`  *(example only; code default `false`)*
- `LANGFUSE_PUBLIC_KEY=lf_pk_local_ai_platform`
- `LANGFUSE_SECRET_KEY=lf_sk_local_ai_platform`
- `LANGFUSE_BASE_URL=http://localhost:3000`  *(example only; code default `https://cloud.langfuse.com`)*

To use a real model, install the relevant LangChain provider package, set the
provider's standard environment variables in your runtime, then set
`CHAT_MODEL` to a native LangChain target such as `openai:gpt-4.1-mini` or
`anthropic:claude-sonnet-4-5`. Knowledge retrieval integrations should pass
LlamaIndex `Document` objects into `KnowledgeRetrievalService` and consume
retrieved `NodeWithScore` values instead of adding template-owned RAG schemas,
rerankers, or vector-store adapters. Retrieval runs on Postgres pgvector
(`RAG_ENABLED` requires `DATABASE_ENABLED`; `RAG_PGVECTOR_TABLE` names the table).

HTTP middleware provides CORS, trusted-host enforcement, a request body limit,
standard error envelopes for FastAPI/Starlette HTTP errors, and access logs with
method, path, status, duration, request id, and authenticated principal when
available.

Endpoints reach the request boundary through small per-concern dependencies,
not a single context object:
`Depends(require_principal)` (`app.modules.platform.identity.auth`) for the
authenticated principal (which also sets `request.state.principal`),
`get_request_id()` (`app.core.request_context`) for the request id, and
`Depends(get_idempotency_key)`
(`app.modules.platform.idempotency.http`) for the optional idempotency key. The
`Idempotency-Key` header is parsed only by endpoints that opt into those
helpers; validation runs regardless of the flag, while `IDEMPOTENCY_ENABLED`
gates the persistence store (calling the replay helpers with the flag off
raises `503 idempotency_disabled`). No shared context object carries Redis,
object storage clients, feature flags, or AI runtimes; add those directly at the
business module boundary when a project actually needs them.

Application wiring is centralized in the bootstrap layer. API routers should
keep only HTTP concerns: path/query/body parsing, response models or envelopes,
and a small call into a business service. Platform modules expose reusable
capabilities such as Mongo, quota, cache, objects, LLM, queues, and task stores;
`app/bootstrap/resources.py` opens those capabilities once for the app.

Business services should receive explicit constructor dependencies and must not
read FastAPI `Request`, `app.state`, or a global service locator. When a product
service needs lifespan-owned runtime dependencies, declare a `Feature` in
`app/bootstrap/features/<domain>.py` and add one entry to `FEATURES` in
`registry.py` (step-by-step: "Add a domain: checklist" in
[template-guide.md](template-guide.md)). Its `build(resources, settings)` runs once per app, after the
platform resources are open, and the instance lives on
`ApplicationResources.services`. Views read it with
`get_app_resources(request.app).service(<Domain>Service)`; no per-surface getter
helpers.

To call an external HTTP API, declare an `Upstream` in the feature's `upstreams`
and use `resources.http(name)` (timeout, retry, circuit breaker and request-id
included); do not build your own `httpx.AsyncClient`.

Adding a new endpoint usually should not touch bootstrap. Add or extend the
business service method, then call it from the API router. Update bootstrap only
when the endpoint introduces a new runtime dependency or a new application
service that must be created once per app lifecycle.

Database access has one pattern: a store takes an
`async_sessionmaker[AsyncSession]` through its constructor, built in
`Feature.build` from `resources.sessionmaker`. A service that needs an explicit
transaction opens it itself with
`async with sessionmaker() as session, session.begin():`. There is no
per-request session dependency. `app/modules/business/conversations` is the
worked example (set `CONVERSATIONS_ENABLED=true` with `DATABASE_ENABLED` and
`LLM_ENABLED`, then apply migration 0010).

Mongo access is an opt-in platform resource. Install the `mongo` extra, set
`MONGO_ENABLED=true`, and build your store in `Feature.build` from
`resources.mongo` (the lifespan-managed `MongoGateway`). Product modules build
their own stores on top of the gateway instead of opening clients or reading
app state directly.

List endpoints take `params: PaginationParams = Depends()` from
`app.core.pagination`, pass `params.limit` and `params.offset` to the store, and
return `build_list_response(items=..., total=..., params=params)` for
offset-based responses:
`{"items": [...], "pagination": {"limit": 50, "offset": 0, "total": 123}}`.
The template intentionally does not ship a generic query builder.

`app.modules.platform.audit.service.record_audit_event(...)` records product
audit events for "who did what to which resource". Audit metadata is guarded against raw prompt,
message, payload, input, output, and generated text keys; store IDs, counts,
status, duration, error codes, and `langfuse_trace_id` instead. Langfuse remains
the place for AI trace details.

When `IDEMPOTENCY_ENABLED=true`,
`app.modules.platform.idempotency.http.get_idempotency_key` validates the
optional `Idempotency-Key` header, and the same
`app.modules.platform.idempotency` package adds concrete persistence with an
`idempotency_keys` table. Request hashes include method, path, body, and
principal id. Reusing the same key with a different request returns
`409 idempotency_key_conflict`; reusing an in-progress key returns
`409 idempotency_key_in_progress`. Streaming responses are intentionally outside
this contract.

Two route guards are provided as opt-in examples; no route in the template
enables them. `require_quota(resource, cost=1)`
(`app.modules.platform.quota.http`) is a dependency that reserves quota for the
principal before the handler runs and answers `429` with `Retry-After` when
exceeded; it needs `QUOTA_ENABLED=true` and a policy for the resource:

```python
@router.post("/reports", dependencies=[Depends(require_quota("reports"))])
async def create_report(...): ...
```

`@idempotent` (`app.modules.platform.idempotency.http`) wraps a synchronous
route that declares `request: Request`. A repeated `Idempotency-Key` replays the
response the first request received without running the handler: the route's
declared `status_code` and the body after `response_model` filtering (any JSON
value: object, list, scalar or null). The request hash covers method, path,
query string, body and principal, so the same key with another query string is a
`409 idempotency_key_conflict`. If the handler raises or is cancelled the key is
released and the next request with it runs the handler again. A handler that
returns a `Response` object is not stored (its key is released). Without the
header the handler runs untouched. It needs `IDEMPOTENCY_ENABLED=true`:

```python
@router.post("/reports")
@idempotent
async def create_report(payload: Payload, request: Request) -> dict: ...
```

Experiment tracking and LLM response caching are intentionally not wrapped by
template adapters in this phase. Object storage (`app/modules/platform/objects`),
queues (`app/modules/messaging/queue`) and OpenTelemetry
(`app/core/telemetry_otel.py`) are wrapped. Use the tools required by the target
project directly at the module boundary for anything else.
Database access goes through stores that take a `sessionmaker` (see above).

Langfuse is only wired at the AI execution boundary. Use
`build_llm_instance(..., instance_id="...", service_name="...")` from
`app.modules.ai.llm.runtime` to create a native LangChain `BaseChatModel` plus a
per-instance Langfuse tracker. Pass `instance.trace_config(...)` into LangChain
calls to keep parallel LLM services separated by instance, service, session,
user, and request metadata.

To use the completions transport, pass a handler factory to `completions_feature`. It runs in lifespan
with the opened resources, so the handler can take an LLM instance, RAG service
or stores from them:

```python
from collections.abc import AsyncIterator

from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from app.bootstrap.application import create_app
from app.bootstrap.features.completions import completions_feature
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings


class MyCompletionHandler:
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return CompletionResult(content="...")

    async def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[CompletionStreamChunk]:
        yield CompletionStreamChunk(delta="...")


def build_handler(resources: ApplicationResources, settings: Settings) -> MyCompletionHandler:
    return MyCompletionHandler()


app = create_app(features=(completions_feature(handler_factory=build_handler),))
```

Without a factory, the scaffold `EchoCompletionHandler` answers. Both processes
read the registry in `app/bootstrap/features/registry.py` (`FEATURES`), so register
your handler factory there (`completions_feature(handler_factory=build_handler)`)
to make the worker run it too. The async task routes (`/api/v1/completions/tasks`) are mounted
only when `TASKS_ENABLED=true`.

The app factory registers a FastAPI lifespan that calls
`langfuse.get_client().flush()` on shutdown when `LANGFUSE_ENABLED=true` and
`init_resources=True`, so any buffered traces from per-instance trackers are
drained before the process exits. The app factory also owns shared runtime
resources on `app.state.resources` (an `ApplicationResources` holding `.engine`,
`.sessionmaker`, and `.redis`); readiness checks and DB dependencies reuse those
handles, and the lifespan closes Redis plus disposes the SQLAlchemy engine on
shutdown.
Tests construct the app with `init_resources=False`, which skips external
readiness checks.

## Bearer Auth

Clients authenticate with an API key sent as `Authorization: Bearer <token>`.
The server stores only SHA-256 digests, in `AUTH_API_KEYS`: comma-separated
entries of

```
subject:scope|scope:sha256hex      # e.g. billing-svc:tasks:read|tasks:write:3f2a...c9
```

(`subject` is everything before the first `:`, the digest everything after the
last; scopes may contain `:` and may be empty, which grants nothing.)

```bash
python -m scripts.hash_api_key --generate   # prints a random token and its digest
# AUTH_API_KEYS=billing-svc:admin:<digest>
curl -X POST http://localhost:8000/api/v1/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "hi"}]}'
```

Tokens must be randomly generated (the digest is unsalted, so a guessable token
is brute-forceable from a leaked config). The presented token's digest is
compared in constant time against every entry.

**Rotation (overlap).** Several entries may share a subject. Add a second entry
for the same subject, roll the client over to the new token, then remove the old
entry. The principal (`subject`) is unchanged throughout, so rate limits, audit
and task ownership carry over.

The subject is the principal id: per-principal rate limiting is therefore
per-client, and `GET /api/v1/completions/tasks/{id}` returns a task only to the
principal that submitted it (404 otherwise). The `Principal` built by
`require_principal` (`app/modules/platform/identity/auth.py`) is
`{"id": subject, "type": "service", "scopes": [...]}` and guards every
`/api/v1/completions*` route. The template intentionally does not create users,
passwords, sessions, or key-management tables. There is no `/auth/me` endpoint — its absence is
pinned by `tests/unit/core/test_application_wiring.py`.
