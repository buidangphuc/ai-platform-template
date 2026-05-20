# Copilot Instructions: AI Solution Engineering Platform

This repository is a reusable FastAPI foundation for AI solution engineering work. Keep generated code aligned with the current platform template and avoid reintroducing legacy business modules.

## Core Rules

- Use Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy async, asyncpg, Redis, pytest, and uv.
- Use `uv run ...` for local commands and `uv sync --dev` for setup.
- Keep imports absolute and rooted in the current app packages.
- Do not add deployment pipelines; this template stops at local Docker build/run.
- Do not add client-specific product domains, hard-coded tenants, or business data.

## Current Structure

```text
app/
  api/                  Versioned FastAPI routers
  bootstrap/            App factory and service wiring
  core/                 Settings, database, Redis, errors, logging, health
  modules/
    feedback/           Feedback schema, model, and repository
    identity/           API key identity model, repository, auth dependency
    rate_limit/         Rate limit service implementations
alembic/                Migration environment
scripts/                Template hygiene checks
tests/                  Unit and integration tests
```

## Implementation Guidance

- Add app behavior through `app/modules/<capability>` and expose it through `app/api/v1/<capability>`.
- Wire services in `app/bootstrap/application.py`.
- Keep provider-specific or optional integrations behind small contracts/adapters.
- Use the standard error envelope from `app.core.errors`.
- Preserve request ID behavior from `app.core.request_context`.
- Keep secrets in settings and `.env`; never commit real secret values.

## Verification

Before considering work complete, run the relevant checks:

```bash
uv run pytest -v
./scripts/check_template_hygiene.sh
```
