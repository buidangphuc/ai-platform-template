# Template Guide — build a new product on this platform

This repo is a **minimal-core template**: a fresh boot serves health + bearer
auth + Swagger and opens **zero** addons. Every capability below is opt-in, so
your product starts simple and grows only where it actually needs to.

Architecture rules live in [agents/architecture.md](agents/architecture.md) — read it before wiring anything. For LLM/RAG/eval work there is a second doc, [agents/ai-engineering.md](agents/ai-engineering.md) (engineering judgment + the repo's AI patterns) — use it alongside, not instead of, the architecture doc. Project facts and checks are indexed in [agents/project.md](agents/project.md).

## 0. Fork checklist

1. Clone/fork, then `cp .env.example .env` and set `AUTH_API_KEYS` (hash tokens with `python -m scripts.hash_api_key --generate`).
2. `make dev` → `curl localhost:8000/healthz` — you have a running core.
3. Rename the project in `pyproject.toml` + `PROJECT_NAME` default.
4. Delete what you won't use: `app/modules/ai/` (and the `[ai]` extra) only if
   the product has no LLM features, which also means removing the
   `conversations` sample and any domain using `LLMInstance`; `alembic/` if no
   Postgres.

## 1. Turn on capabilities as you need them

| Need | Flip in `.env` | Backing service |
|---|---|---|
| Postgres (SQLAlchemy + Alembic) | `DATABASE_ENABLED=true` + `POSTGRES_*` | postgres |
| Redis | `REDIS_ENABLED=true` + `REDIS_*` | redis |
| Async jobs (queue + tasks + worker) | `QUEUE_ENABLED=true TASKS_ENABLED=true` | redis (or sqs/rabbitmq) + postgres or redis task store |
| Rate limiting | `RATE_LIMIT_ENABLED=true` | redis |
| Caching | `CACHE_ENABLED=true` | redis |
| Object storage | `OBJECTS_ENABLED=true` | S3 (`uv sync --extra aws`) |
| MongoDB | `MONGO_ENABLED=true` | mongo (`--extra mongo`) |
| Idempotency keys | `IDEMPOTENCY_ENABLED=true` | postgres |
| Outbox | `OUTBOX_ENABLED=true` | postgres |
| Webhooks | `WEBHOOKS_ENABLED=true` + `WEBHOOK_SIGNING_SECRET` | none (outbound HTTP) |
| Quota | `QUOTA_ENABLED=true` | postgres/mongo |
| LLM + tracing + RAG | `uv sync --extra ai`, then `CHAT_MODEL=...`, `LANGFUSE_ENABLED`, `RAG_ENABLED` | provider keys / langfuse |

The standard stack for a typical service is DATABASE + REDIS + QUEUE + TASKS +
RATE_LIMIT. [`ops/compose/local.yaml`](../ops/compose/local.yaml) is the worked example of the
whole stack except rate limit: a one-shot `migrate` service (`alembic upgrade head`), then api + worker
+ postgres + redis with DATABASE, REDIS, QUEUE and TASKS on; the api listens on `127.0.0.1` only. Flip `RATE_LIMIT_ENABLED` in `.env` on top of it. The worker is
`python -m scripts.run_worker`, the same command `make worker` runs locally.

## 2. Add a business domain (the one pattern to copy)

```text
app/modules/business/<domain>/
  schemas.py        # request/result Pydantic models
  types.py          # enums/constants
  service.py        # <Domain>Service — constructor deps only, no Request/app.state
  stores/           # own the table/collection details
  integrations/     # external HTTP APIs — __init__(self, client: UpstreamClient, ...plain options)
app/api/v1/<domain>/
  router.py         # thin endpoints: get_app_resources(request.app).service(<Domain>Service) -> one call;
                    # declares its own prefix and Depends(require_principal)
  tasks.py          # only for task_routers (mounted when TASKS_ENABLED)
app/bootstrap/features/<domain>.py
  <domain>_feature(...) -> Feature: service type, build(resources, settings),
  routers, task_routers, tasks (type -> handler), models, enabled(settings)
app/bootstrap/features/registry.py
  one entry in FEATURES; create_app, the worker and alembic/env.py read it
app/core/config/<domain>.py
  <Domain>SettingsMixin(BaseModel) — *_ENABLED defaults False; add to Settings
```

A new domain is one file under `app/bootstrap/features/` plus one entry in
`registry.py`; no edit to `resources.py`, `services.py`, `api/router.py`,
`worker.py` or `alembic/env.py`. If the domain needs a new lifecycle resource,
add an addon in `app/bootstrap/addons/base.py:default_resource_addons()`. The
`completions` surface is the living reference for the thin-transport shape; its
handler comes from `completions_feature(handler_factory=...)`.

> **Deliberate: no structured-output enforcement at the transport.** The
> completions contract serves both sync and streaming, and schema validation
> needs the complete output — enforcing it would break the stream path.
> A product that needs guaranteed JSON applies `with_structured_output` on
> its own sync endpoint only.

### Add a domain: checklist

0. Run `make new-domain NAME=<domain>`. It generates the files below and registers them.
1. Generated: `app/modules/business/<domain>/` (`schemas.py`, `service.py`) and `app/api/v1/<domain>/router.py`. Edit: replace the echo service; add stores and integrations as needed.
2. Generated: `<domain>_feature()` in `app/bootstrap/features/<domain>.py`. Edit: wire your constructor dependencies in `build`. A task handler lives in this file: `async def handler(resources, task) -> dict`, parsing `task.payload` with the request schema and raising on failure so the worker marks the task failed. Register it in `tasks={TYPE: handler}`.
3. Generated: `app/core/config/<domain>.py` with `<Domain>SettingsMixin(BaseModel)`, added to the `Settings` bases. Edit: add cross-setting rules in a `@model_validator`.
4. Generated: `<DOMAIN>_ENABLED=false` in `.env.example` (`scripts/check_env_example.py` fails on drift). Edit: add any further keys you introduce.
5. Generated: one entry in `FEATURES` in `app/bootstrap/features/registry.py`.
6. Auth: declare `dependencies=[Depends(require_principal)]` once on the router; add `principal: Principal = Depends(require_principal)` to a route only when it needs the id. A missing token answers 401.
7. Tests: see "Testing a feature" in [agents/architecture.md](agents/architecture.md).

Stores take an `async_sessionmaker` (or `MongoGateway`) through their constructor,
built in `Feature.build` from `resources.sessionmaker` / `resources.mongo`; there is
no per-request session dependency. `conversations` (Postgres + LLM, behind
`CONVERSATIONS_ENABLED`) is the worked example. A fork without a chatbot deletes
`app/modules/business/conversations`, `app/api/v1/conversations`,
`app/bootstrap/features/conversations.py` and its entry in `registry.py`,
`app/core/config/conversations.py` (plus its entry in the `Settings` bases and the
`.env.example` line) and migration `0010_create_conversations`.

Rules that keep the template clean (enforced by `make arch` and review, spelled out in
[agents/architecture.md](agents/architecture.md)): endpoints never build clients/stores; business services never
read `Request`/`app.state`; touch bootstrap only for app-lifetime resources.

## 3. Optional installs (extras)

| Extra | Brings | Needed for |
|---|---|---|
| `ai` | langchain, langchain-openai, langfuse, llama-index-core, llama-index-vector-stores-postgres | `app/modules/ai/*` (LLM router, tracing, RAG) |
| `aws` | aioboto3 | S3 object storage, SQS queue |
| `mongo` | motor, pymongo | Mongo gateway |
| `rabbitmq` | aio-pika | RabbitMQ queue backend |
| `otel` | opentelemetry-api, opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http, opentelemetry-instrumentation-fastapi | OpenTelemetry traces and GenAI metrics (`OTEL_ENABLED=true`) |

RabbitMQ `receive_count` drives dead-lettering after repeated failures. On a classic queue a message that keeps crashing the worker is only flagged "redelivered", so its count stops at 2. Set `RABBITMQ_QUEUE_TYPE=quorum` (or create the queue in a vhost whose default type is quorum) to get an exact count from the broker. Empty keeps the vhost default; changing the type of an existing queue requires deleting it first.

Task delivery is at-least-once. `submit` stores the task and then sends one
queue message; if the send fails the task stays `queued`. The worker's reclaim
loop (`TASKS_RECLAIM_INTERVAL_SECONDS`) announces again every task that stayed
`queued` for `TASKS_QUEUED_REANNOUNCE_SECONDS` and requeues `processing` tasks
whose lease expired, so a task can be delivered twice and a handler must be
idempotent. A handler runs under a timeout of `TASKS_LEASE_SECONDS`: it is
cancelled, the task fails with `lease_exceeded` and the message is dead-lettered.
A result that arrives after the task was settled is dropped (logged as
`worker.result_dropped`), never written over the stored one.

Dev installs everything: `uv sync --dev --all-extras` (what `make test` uses).
A missing extra fails with an actionable message at the feature's entry point
(see `app/modules/ai/_deps.py`), never at import/boot time.

## 4. Observability (deliberately not shipped)

The template ships **no metrics endpoint and no monitoring stack** — that's
per-project by design. When your product needs it, the recipe is small:

1. Request metrics: add a `/metrics` endpoint (stdlib text exposition or
   `prometheus-fastapi-instrumentator`) behind your product's enable flag.
2. Stack: a compose overlay with Prometheus (+ scrape config), Grafana
   (provisioned datasource + dashboard), Loki+Promtail for logs,
   Alertmanager for rules — layer it like `ops/compose/langfuse.yaml`.
3. Container CPU/mem: add cadvisor; GPU needs nvidia-dcgm-exporter on a
   GPU host.

## 5. Serving a model behind the API

The API never loads model weights — it calls a **model server** over HTTP.
The ready-made half of that contract is
`app/modules/platform/model_server/client.py`: `ModelServerClient`
(predict + ping, unreachable → clean 503) speaks the ML pipeline template's
serving image out of the box:

```text
POST /predict {"text": "..."}  -> {"label": "...", "score": 0.97}   (or texts:[...] batch)
GET  /health · GET /metrics
```

Declare the server as an `Upstream` on your `Feature` and hand the resolved
client to `ModelServerClient` (timeout, retry on transient failures, circuit
breaker and `X-Request-ID` come with it; bootstrap opens and closes it):

```python
Feature(
    name="classify",
    service=ClassifyService,
    upstreams=(
        Upstream(
            "model_server",
            base_url=lambda settings: settings.MY_MODEL_URL,
            timeout=10.0,
            retries=1,
        ),
    ),
    build=lambda res, settings: ClassifyService(
        ModelServerClient(res.http("model_server"))
    ),
)
```

Any HTTP model server fits: the ML template's `Dockerfile.serve` container,
vLLM/TGI/llama.cpp for LLMs (OpenAI-compatible servers plug into the `[ai]`
LangChain client through the provider's base-URL env var, e.g. `OPENAI_BASE_URL`), or a managed endpoint. Add it as a compose
service — profile-gate it if it needs a GPU — and select the backend with a
settings flag so a stub/fallback path keeps working without it.

RAG stores vectors in Postgres (`RAG_BACKEND=pgvector`, table
`data_<RAG_PGVECTOR_TABLE>`, created at startup by the vector store; the app
role cannot `CREATE EXTENSION`, so the database must already have `vector`).
`build_vector_store`/`build_embed_model` are the extension points — plug in
another LlamaIndex vector store or an embedding provider without touching the
service.

## 6. Test layout

- `tests/unit/` — service/module behavior, no app boot needed.
- `tests/integration/` — API contract tests driving the real app; opt-in
  addons are enabled per test via settings overrides.
- `tests/conftest.py` — fixtures: `test_settings` (safe test Settings),
  `client` (ASGI test client, `init_resources=False`), `auth_headers`
  (`Bearer test-token`).
- `tests/factories.py` — `build_test_settings(**overrides)` is how every
  test flips capability flags; `api_client_for(app)` for custom apps.
- Fast loop: `make test-fast` (parallel) · one file:
  `uv run --all-extras pytest tests/unit/... -q`.

## 7. Verify as you go

`make test` (`pytest -m "not infra"`) · `make test-infra` (everything, on localinfra) · `make lint` + `make typecheck` · `make dev` for
the live server · `make docker-run` for the composed standard stack ·
`make docker-run-langfuse` to layer self-hosted tracing.
