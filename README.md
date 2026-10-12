# AI Solution Engineering Platform

Reusable FastAPI foundation for AI solution engineering work. The template keeps the app shell, security baseline, and local data services clean so project-specific AI product code can be added without inheriting old business coupling.

## Scope

The repository covers the local application foundation:

- Import-safe FastAPI app factory, Pydantic settings and `.env` workflow.
- Health/readiness endpoints, request IDs, logging context, standard error envelope.
- API-key Bearer authentication with per-client principals and per-owner task access.
- Central composition root for project services built from platform resources.
- Product primitives: per-concern request dependencies, explicit DB transactions, pagination, audit events, idempotency, rate limiting.
- LangChain chat model wiring with per-instance Langfuse tracking, and LlamaIndex retrieval support code.
- Self-hosted Langfuse local stack, PostgreSQL with Alembic, local Docker build/run path.

Deployment pipelines are intentionally out of scope. Each team or client environment can bring its own deployment platform.

## Minimal core and opt-in capabilities

A fresh boot opens **zero addons**: app factory, bearer auth, health probes, and Swagger only. No database, Redis, queue, or AI packages are required.

Every capability (Postgres, Redis, queue and tasks, rate limit, cache, objects, Mongo, idempotency, outbox, webhooks, quota) is enabled by its `*_ENABLED` flag. The LLM/RAG/tracing stack installs separately via the `ai` extra (`uv sync --extra ai`). The [template guide](docs/template-guide.md) has the capability table and the add-a-domain walkthrough.

## Project layout

```text
app/
  api/                  Versioned FastAPI routers
  bootstrap/            App factory, platform resources, and service wiring
  core/                 Settings, database, Redis, errors, logging, health
  modules/
    ai/                 llm/ (LangChain + Langfuse), rag/ (LlamaIndex), evals/
    business/           Domain logic (completions transport scaffold)
    messaging/          outbox/, queue/, tasks/, webhooks/
    platform/           identity/, audit/, idempotency/, rate_limit/, cache/,
                        objects/, mongo/, quota/, model_server/
alembic/                Migration environment
docs/                   usage.md, template-guide.md, adr/, migration/, agents/
evals/                  Eval cases for the eval gate
ops/
  compose/              Docker Compose stacks: local.yaml, langfuse.yaml, langfuse.env.example
  mlops/                MLflow local env example
  observability/        OpenTelemetry collector debug config
openspec/               Specs and change proposals
scripts/                Local helper scripts (including Langfuse smoke runners)
tests/                  Unit and integration tests
```

## Quickstart

```bash
cp .env.example .env
uv sync --dev
make test
make dev
curl http://localhost:8000/healthz
```

The API starts on `http://localhost:8000`. For Docker, Langfuse, configuration and auth, see [docs/usage.md](docs/usage.md).

## Documentation

- [docs/usage.md](docs/usage.md): requirements, quickstart, Docker, commands, env defaults, bearer auth.
- [docs/template-guide.md](docs/template-guide.md): fork checklist, enabling capabilities, adding a business domain.
- [docs/agents/project.md](docs/agents/project.md): feedback loops, checks, and an index of the architecture and AI-engineering docs.
- [docs/adr/](docs/adr/): architecture decision records.
- [openspec/](openspec/): specs and change proposals.
- [ops/compose/local.yaml](ops/compose/local.yaml) and [ops/compose/langfuse.yaml](ops/compose/langfuse.yaml): local Docker stacks.
