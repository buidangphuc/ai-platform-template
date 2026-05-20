# Simplified Runtime and Database Session Design

Date: 2026-05-20
Status: Accepted
Scope: Current implementation target after the LangChain/LlamaIndex discussion.

## Decisions

1. Do not keep a template-owned adapter registry in this phase.
2. Keep LangChain, LangGraph, and LlamaIndex support as module-level building blocks, not app startup dependencies.
3. Use LlamaIndex directly for research/eval or project-specific advanced retrieval code; it is not mounted as a standalone answer product.
4. Skip app observability adapters, experiment trackers, object storage adapters, job queue adapters, and LLM response caching in this phase.
5. Keep stable Pydantic payload schemas where they protect API flow, but place them with the module that owns them: agents, RAG, evals, feedback, usage, and research artifact manifests.
6. Database access is not an adapter. Modules that need persistence should accept `app.core.database.DbSession`, use SQLAlchemy models/repositories in their own module, and keep transactions explicit at the request/service boundary.

## Runtime Wiring

`create_app()` wires only the base app shell:

- settings
- logging
- health/readiness checks
- API key auth repository
- feedback repository
- fixed-window rate limiter
- request ID middleware
- exception handlers
- basic API routers

There is no `app.state.adapters`, no registry object, no `app/contracts`
folder, no AI runtime state, and no app observability client in the golden path.

## Database Rule

The database primitive is:

```python
from app.core.database import DbSession
```

Routes or services that need persistence should receive `DbSession` through FastAPI dependency injection and pass the session into module-local repositories. Do not create a database adapter layer or a global DB service registry.

## Retrieval Rule

RAG, eval, and agent modules are support code. The template does not mount
`/api/v1/rag/*`, `/api/v1/evals/*`, or `/api/v1/agents/*` by default because
those routes only make sense once a downstream product defines the business
workflow that calls them.

## Deferred

- App observability/tracing export.
- Langfuse, MLflow, LangSmith, Datadog, Grafana, Phoenix, or other vendor tooling.
- LLM response cache policy.
- Object storage and background job infrastructure.
- Deployment pipeline.
