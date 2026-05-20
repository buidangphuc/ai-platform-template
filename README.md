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
    feedback/           Feedback schema, model, and repository
    identity/           API key identity model, repository, auth dependency
    rate_limit/         Rate limit service contracts and implementations
alembic/                Migration environment
scripts/                Local helper scripts
tests/                  Unit and integration tests
```

## Local Commands

```bash
make dev          # run local API with uvicorn reload
make test         # run full pytest suite
make eval-smoke   # run feedback/evaluation smoke test
make hygiene      # check stale template coupling
```

## Secrets

Copy `.env.example` to `.env` for local development. Keep real secrets in environment variables or your team's secret manager, not in Git.

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
