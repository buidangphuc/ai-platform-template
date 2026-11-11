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
| Async jobs (queue + tasks + worker) | `QUEUE_ENABLED=true TASKS_ENABLED=true` | redis (or memory/sqs/rabbitmq) |
| Rate limiting | `RATE_LIMIT_ENABLED=true` | memory or redis |
| Caching | `CACHE_ENABLED=true` | memory or redis |
| Object storage | `OBJECTS_ENABLED=true` | memory or S3 (`uv sync --extra aws`) |
| MongoDB | `MONGO_ENABLED=true` | mongo (`--extra mongo`) |
| Idempotency keys | `IDEMPOTENCY_ENABLED=true` | postgres |
| Outbox / webhooks | `OUTBOX_ENABLED` / `WEBHOOKS_ENABLED` | postgres |
| Quota | `QUOTA_ENABLED=true` | memory/postgres/mongo |
| LLM + tracing + RAG | `uv sync --extra ai`, then `CHAT_MODEL=...`, `LANGFUSE_ENABLED`, `RAG_ENABLED` | provider keys / langfuse |

The standard stack for a typical service is DATABASE + REDIS + QUEUE + TASKS +
RATE_LIMIT. [`ops/compose/local.yaml`](../ops/compose/local.yaml) is the worked example of the
DATABASE + REDIS half; flip `QUEUE_ENABLED`/`TASKS_ENABLED`/`RATE_LIMIT_ENABLED`
in `.env` on top of it, and when you enable TASKS add a second compose service
running the worker (`python -m scripts.run_worker` — the same command
`make worker` runs locally).

## 2. Add a business domain (the one pattern to copy)

```text
app/modules/business/<domain>/
  schemas.py        # request/result Pydantic models
  types.py          # enums/constants
  service.py        # <Domain>Service — constructor deps only, no Request/app.state
  stores/           # own the table/collection details
  integrations/     # external HTTP APIs — __init__(self, client: UpstreamClient, ...plain options)
app/api/v1/<domain>/
  router.py         # mounts leaf routers, attaches Depends(require_principal)
  <leaf>.py         # thin endpoints: get_app_resources(request.app).service(<Domain>Service) -> one call
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

1. Create `app/modules/business/<domain>/` (`schemas.py`, `service.py`, plus stores/integrations as needed) and `app/api/v1/<domain>/router.py`.
2. Write `<domain>_feature()` in `app/bootstrap/features/<domain>.py` returning a `Feature`. A task handler lives in this file: `async def handler(resources, task) -> dict`, parsing `task.payload` with the request schema and raising on failure so the worker marks the task failed. Register it in `tasks={TYPE: handler}`.
3. Settings: new file `app/core/config/<domain>.py` with `<Domain>SettingsMixin(BaseModel)`; import it and add it to the `Settings` bases in `app/core/config/__init__.py` (two edits).
4. Add the new keys to `.env.example` (`scripts/check_env_example.py` fails on drift).
5. Add one entry to `FEATURES` in `app/bootstrap/features/registry.py`.
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

Rules that keep the template clean (enforced by review, spelled out in
[agents/architecture.md](agents/architecture.md)): endpoints never build clients/stores; business services never
read `Request`/`app.state`; touch bootstrap only for app-lifetime resources.

## 3. Optional installs (extras)

| Extra | Brings | Needed for |
|---|---|---|
| `ai` | langchain, langchain-openai, langfuse, llama-index-core, openai | `app/modules/ai/*` (LLM router, tracing, RAG) |
| `aws` | aioboto3 | S3 object storage, SQS queue |
| `mongo` | motor, pymongo | Mongo gateway |
| `rabbitmq` | aio-pika | RabbitMQ queue backend |

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
LangChain client via `base_url`), or a managed endpoint. Add it as a compose
service — profile-gate it if it needs a GPU — and select the backend with a
settings flag so a stub/fallback path keeps working without it.

RAG storage scales the same way: `build_storage_context`/`build_embed_model`
raise at the extension points — plug in LlamaIndex's ecosystem
(`llama-index-vector-stores-qdrant`, `-postgres`, embedding providers)
without touching the service.

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

`make test` (full pytest) · `make lint` + `make typecheck` · `make dev` for
the live server · `make docker-run` for the composed standard stack ·
`make docker-run-langfuse` to layer self-hosted tracing.
