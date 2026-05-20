# Simplified Runtime and Database Session Design

Date: 2026-05-20
Status: Accepted
Scope: Current implementation target after the LangChain/LlamaIndex discussion.

## Decisions

1. Do not keep a template-owned adapter registry in this phase.
2. Keep LangChain, LangGraph, and LlamaIndex support as module-level building blocks, not app startup dependencies.
3. Use LlamaIndex directly for research/eval or project-specific advanced retrieval code; it is not mounted as a standalone answer product.
4. Skip app observability adapters, local experiment trackers, local prompt registries, local usage tracking, object storage adapters, job queue adapters, and LLM response caching in this phase. AI execution tracing, prompt lookup, and custom eval scores use Langfuse at the LLM boundary.
5. Keep stable Pydantic payload schemas where they protect API flow, but place them with the module that owns them: API identity and research artifact manifests. RAG uses LlamaIndex `Document` and `NodeWithScore` directly, and agents use LangGraph `MessagesState` directly, instead of local request/response schemas.
6. Database access is not an adapter. Modules that need persistence should accept `app.core.database.DbSession`, use SQLAlchemy models/repositories in their own module, and keep transactions explicit at the request/service boundary.

## Runtime Wiring

`create_app()` wires only the base app shell:

- settings
- logging
- health/readiness checks
- API key auth repository
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

`app/modules/rag` must stay thin over LlamaIndex. It accepts LlamaIndex
`Document` objects for indexing and returns LlamaIndex `NodeWithScore` values
for retrieval. Local RAG schemas, custom rerankers, and vector-store adapters are
out of scope unless a downstream project has a concrete product reason to add
them.

## Deferred

- App observability/tracing export.
- Business-specific feedback capture.
- Business-specific eval pipelines.
- MLflow, LangSmith, Datadog, Grafana, Phoenix, or other vendor tooling.
- LLM response cache policy.
- Object storage and background job infrastructure.
- Deployment pipeline.

## Langfuse Rule

Langfuse is not an app-wide observability adapter. It is used only where LLM,
LangChain, or LangGraph execution happens. Each logical LLM service should
create its own `LLMInstance` with a stable `instance_id` and `service_name`, then
pass `instance.trace_config(...)` into LangChain or LangGraph calls. This keeps
parallel LLM services separated in Langfuse traces, usage views, prompt
versions, and eval scores.

Local development uses the self-hosted Langfuse Docker stack and headless
initialization from `.env`; no cloud credentials are required.
