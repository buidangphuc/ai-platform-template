# AI Solution Engineering Platform

Reusable FastAPI foundation for AI solution engineering work. The template keeps the app shell, security baseline, and local data services clean so project-specific AI product code can be added without inheriting old business coupling.

## Scope

This repository currently covers the local application foundation:

- Import-safe FastAPI app factory.
- Pydantic settings and `.env` workflow.
- Health/readiness endpoints.
- Request ID middleware, logging context, and standard error envelope.
- API key bootstrap and authentication.
- Fixed-window rate limiting foundation.
- Native LangChain chat model wiring and LangGraph `MessagesState` graph builder.
- LlamaIndex advanced retrieval support code using native `Document` and
  `NodeWithScore` primitives, retrieval smoke checks, and redaction policy.
- Research workspace with sample datasets, artifact manifests, and smoke evals.
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

- `GET /health`
- `GET /ready`
- `POST /api/v1/auth/api-keys`
- `GET /api/v1/auth/me`

All `/api/v1/*` platform endpoints except health and API-key bootstrap require
`Authorization: Bearer <api-key>`.

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
    agents/             Native LangGraph agent graph factory
    identity/           API key identity model, repository, auth dependency
    rag/                LlamaIndex-backed retrieval support for agents
    rate_limit/         Rate limit service contracts and implementations
alembic/                Migration environment
research/               Datasets, evals, training templates, artifact manifests
scripts/                Local helper scripts
tests/                  Unit and integration tests
```

## Local Commands

```bash
make dev          # run local API with uvicorn reload
make test         # run full pytest suite
make eval-smoke   # run local RAG evaluation smoke test
make hygiene      # check stale template coupling
```

## Secrets

Copy `.env.example` to `.env` for local development. Keep real secrets in environment variables or your team's secret manager, not in Git.

## Runtime Defaults

The template boots without cloud credentials. The app factory does not create AI
runtime services by default; project business logic can wire LangChain,
LangGraph, or LlamaIndex services where it actually needs them. Local research
smoke tests still use fake/mock AI primitives outside the API app.

- `CHAT_PROVIDER=`
- `CHAT_MODEL_NAME=`
- `LANGFUSE_ENABLED=true`
- `LANGFUSE_PUBLIC_KEY=lf_pk_local_ai_platform`
- `LANGFUSE_SECRET_KEY=lf_sk_local_ai_platform`
- `LANGFUSE_BASE_URL=http://localhost:3000`

To use a real model, install the relevant LangChain provider package, set the
provider's standard environment variables in your runtime, then set
`CHAT_PROVIDER` and `CHAT_MODEL_NAME` to a supported pair (see
`app/core/config.py::CHAT_MODELS_BY_PROVIDER`). Knowledge retrieval integrations should pass LlamaIndex
`Document` objects into `KnowledgeRetrievalService` and consume retrieved
`NodeWithScore` values instead of adding template-owned RAG schemas, rerankers,
or vector-store adapters.

App observability, experiment tracking, LLM response caching, object storage,
and job queues are intentionally not wrapped by template adapters in this phase.
Use the tools required by the target project directly at the module boundary.
Database access goes through `app.core.database.DbSession`, a normal SQLAlchemy
session dependency.

Langfuse is only wired at the AI execution boundary. Use
`build_llm_instance(..., instance_id="...", service_name="...")` to create a
native LangChain `BaseChatModel` plus a per-instance Langfuse tracker. Pass
`instance.trace_config(...)` into LangChain or LangGraph calls to keep parallel
LLM services separated by instance, service, session, user, and request
metadata.

The app factory registers a FastAPI lifespan that calls
`langfuse.get_client().flush()` on shutdown when `LANGFUSE_ENABLED=true` and
`init_resources=True`, so any buffered traces from per-instance trackers are
drained before the process exits. Tests construct the app with
`init_resources=False`, which skips the flush hook.

## Research Workspace

Phase 4 adds a local-first `research/` workspace:

- `research/datasets/samples/rag_smoke.jsonl`
- `research/datasets/schemas/rag_eval_case.schema.json`
- `research/evaluation/run_rag_smoke.py`
- `research/evaluation/metrics/keyword_hit_rate.py`
- `research/training/train_template.py`
- `research/artifacts/sample_prompt_manifest.yaml`

Run the local smoke eval with:

```bash
make eval-smoke
```

The smoke command uses local fake/mock primitives and writes a report under
`research/evaluation/reports/`. Generated reports are ignored by Git.

## API Key Bootstrap

Set `API_KEY_BOOTSTRAP_TOKEN` in `.env`, then create an API key:

```bash
curl -X POST http://localhost:8000/api/v1/auth/api-keys \
  -H "Content-Type: application/json" \
  -H "X-Bootstrap-Token: $API_KEY_BOOTSTRAP_TOKEN" \
  -d '{"name":"local"}'
```

Use the returned key with:

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <api-key>"
```
