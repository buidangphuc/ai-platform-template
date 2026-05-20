# AI Solution Engineering Platform

Reusable FastAPI foundation for AI solution engineering work. The template keeps the app shell, security baseline, local data services, and feedback/evaluation capture points clean so project-specific AI product code can be added without inheriting old business coupling.

## Scope

This repository currently covers the local application foundation:

- Import-safe FastAPI app factory.
- Pydantic settings and `.env` workflow.
- Health/readiness endpoints.
- Request ID middleware, logging context, and standard error envelope.
- API key bootstrap and authentication.
- Fixed-window rate limiting foundation.
- Feedback capture schema and endpoint.
- Native LangChain chat model wiring and LangGraph-ready agent runtime.
- Prompt registry, optional LlamaIndex advanced retrieval, retrieval evaluation, usage tracking, and redaction policy.
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
- `POST /api/v1/feedback`

All `/api/v1/*` platform endpoints except health and API-key bootstrap require
`Authorization: Bearer <api-key>`.

## Docker

```bash
cp .env.example .env
make docker-build
make docker-run
```

The Docker path is a local golden path only. It builds the API image and runs the API, PostgreSQL, and Redis with `docker-compose.local.yaml`.

## Project Layout

```text
app/
  api/                  Versioned FastAPI routers
  bootstrap/            App factory and service wiring
  core/                 Settings, database, Redis, errors, logging, health
  modules/
    agents/             Agent API schemas and LangGraph-backed runtime
    feedback/           Feedback schema, model, and repository
    identity/           API key identity model, repository, auth dependency
    prompts/            In-memory prompt registry and default agent prompt
    rag/                LlamaIndex-backed knowledge ingestion and retrieval
    evals/              Local retrieval evaluation service
    usage/              In-memory usage/cost/latency records
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

- `CHAT_MODEL=`

To use a real model, install the relevant LangChain provider package, set the
provider's standard environment variables in your runtime, then set
`CHAT_MODEL`. Knowledge retrieval integrations should be wired through
LlamaIndex primitives at the `KnowledgeRetrievalService` boundary instead of
adding a template-owned vector-store adapter.

App observability, experiment tracking, LLM response caching, object storage,
and job queues are intentionally not wrapped by template adapters in this phase.
Use the tools required by the target project directly at the module boundary.
Database access goes through `app.core.database.DbSession`, a normal SQLAlchemy
session dependency.

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

## Feedback Capture

The feedback endpoint stores lightweight records through an in-memory repository for now. The SQLAlchemy model is present so database persistence can be added later without changing the public payload contract.

```bash
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req_1",
    "trace_id": "trace_1",
    "target_type": "llm_response",
    "target_id": "resp_1",
    "rating": "negative",
    "labels": ["hallucination"],
    "comment": "Answer cited the wrong source"
  }'
```
