# AI Solution Engineering Platform

Reusable FastAPI foundation for AI solution engineering work. The template keeps the app shell, security baseline, and local data services clean so project-specific AI product code can be added without inheriting old business coupling.

## What's included

- Import-safe FastAPI app factory with a centralized composition root.
- Pydantic settings and a `.env` workflow.
- Health/readiness endpoints, request-ID middleware, logging context, and a standard error envelope.
- Static Bearer token authentication with a configurable local principal.
- Lean product primitives: service context, explicit DB transactions, pagination schemas, audit events, and idempotency persistence.
- Fixed-window rate limiting foundation.
- Native LangChain chat model wiring with a per-instance Langfuse tracker.
- LlamaIndex advanced retrieval support using native `Document` and `NodeWithScore` primitives, retrieval smoke checks, and a redaction policy.
- Self-hosted Langfuse local stack (Docker Compose) for tracing, prompt management, and eval scores.
- PostgreSQL model metadata with Alembic, plus opt-in Mongo as a platform resource.
- Local Docker build/run path.

Deployment pipelines are intentionally out of scope — each team or client environment brings its own deployment platform.

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

## Endpoints

- `GET /healthz` — liveness probe (always 200 while the process is alive)
- `GET /readyz` — readiness probe (503 when Postgres/Redis are unreachable)
- `GET /api/v1/auth/me` — returns the configured local principal
- `POST /api/v1/completions` — single JSON completion
- `POST /api/v1/completions/stream` — server-sent stream deltas

All `/api/v1/*` endpoints except the health checks require `Authorization: Bearer <AUTH_BEARER_TOKEN>`.

The completions endpoints are thin transport skeletons: they accept chat messages, call an injected `CompletionHandler`, and return either one completion or stream deltas — no prompt templates, model selection, caching, retrieval, or product workflow logic. Without an injected handler they return `501 completion_handler_not_configured`.

## Docker

```bash
cp .env.example .env
make docker-build
make docker-run
```

This is a local golden path only — it builds the API image and runs the API, PostgreSQL, and Redis via `docker-compose.local.yaml`.

To run the API with the self-hosted Langfuse stack for AI tracing, prompt management, and eval scores:

```bash
cp .env.example .env
make docker-run-langfuse
```

Langfuse is available at `http://localhost:3000`. The local project and API keys are bootstrapped from `.env` through Langfuse headless initialization. The API container uses `LANGFUSE_DOCKER_BASE_URL=http://langfuse-web:3000`; host Python processes use `LANGFUSE_BASE_URL=http://localhost:3000`.

## Project layout

```text
app/
  api/                  Versioned FastAPI routers (transport layer)
  bootstrap/            App factory, lifespan resources, and service wiring
  core/                 Settings, database, Redis, errors, logging, health, middleware
  modules/
    platform/           Reusable capabilities (e.g. Mongo) opened once per app
    identity/           Static Bearer principal and auth dependency
    audit/              Product audit events for actor/resource/action history
    idempotency/        Concrete idempotency-key persistence helpers
    llm/                LangChain chat model factory and per-instance Langfuse tracker
    rag/                LlamaIndex-backed knowledge retrieval and tool builders
    rate_limit/         Rate limit service contracts and implementations
alembic/                Migration environment
scripts/                Local helper scripts (including Langfuse smoke runners)
tests/                  Unit and integration tests
docs/                   Design specs and implementation plans
```

## Local commands

```bash
make dev                    # run local API with uvicorn reload
make test                   # run full pytest suite
make smoke-langfuse         # exercise the Langfuse callback against the local stack
make smoke-langfuse-prompt  # exercise the Langfuse prompt-management flow
make hygiene                # check for stale template coupling
```

## Configuration

Copy `.env.example` to `.env` for local development. Keep real secrets in environment variables or your team's secret manager, never in Git.

The template boots without cloud credentials and creates no AI runtime services by default — project code wires LangChain or LlamaIndex where it actually needs them. Key defaults:

- `CHAT_MODEL=` — empty; set a native LangChain target (e.g. `openai:gpt-4.1-mini`, `anthropic:claude-sonnet-4-5`) once the provider package and its env vars are present
- `AUTH_BEARER_TOKEN=change-me-local-bearer-token`
- `AUTH_SUBJECT=local-user`, `AUTH_ROLES=admin` — define the local principal
- `MONGO_ENABLED=false` — opt-in Mongo platform resource
- `IDEMPOTENCY_ENABLED=false` — when false, incoming `Idempotency-Key` headers are ignored
- `CORS_ALLOW_ORIGINS=*`, `TRUSTED_HOSTS=*`, `MAX_REQUEST_BODY_BYTES=10485760`
- `LANGFUSE_ENABLED=true` with local `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL`

See `.env.example` for the full set.

## Building on the template

How to add endpoints and business services, where wiring lives, the platform/business/API boundary, and the legacy/DGL migration path are documented in the repo-local agent skill — the single source of truth for both humans and AI agents:

- `.agents/fastapi-template-repo/SKILL.md` — architecture overview and the add-a-service workflow.
- `.agents/fastapi-template-repo/references/architecture.md` — layer boundaries, adding endpoints/services, and migration details.
- `.agents/senior-ai-engineer/` — engineering discipline plus the repo's LLM/RAG/eval patterns.
- `AGENTS.md` / `CLAUDE.md` — entry points that route agents to the skills above.
- `docs/` — design specs and implementation plans behind the current foundation.
