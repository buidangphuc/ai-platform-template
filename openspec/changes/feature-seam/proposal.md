## Why

A new product feature (DGL migration, chatbot) should need business code only. Today it does not:

- `app/bootstrap/application.py:28` and `app/bootstrap/worker.py:140` take `completion_handler_factory` / `completion_guards_factory`, so the app factory is named after one example domain. `scripts/run_worker.py:22` passes neither, so the worker always runs the echo handler.
- `app/bootstrap/worker.py:104` turns every task into `CompletionRequest` and ignores `task.type`; a second domain cannot have background tasks.
- A second domain edits `bootstrap/resources.py`, `bootstrap/services.py`, `api/router.py`, `bootstrap/worker.py` and `alembic/env.py`.
- No resource builds an `LLMInstance`; `LLM_*` settings do not affect `/completions`; `handlers/echo.py` is the only handler.
- Observation (`CompletionSink`) lives in `CompletionService`, so a second LLM domain re-implements it.
- No shared outbound HTTP; `app/bootstrap/addons/webhooks.py` builds its own client.
- Docs teach `DbSession` / `MongoDep` (per request) while services are singletons and every real store takes a `sessionmaker`.
- Quota and idempotency need hand-written calls in each view.

## What changes

1. `Feature` declaration + `FEATURES` registry: routes, service build, task handlers, ORM models, upstreams. `create_app`, `worker_context` and `alembic/env.py` read it. `resources.service(cls)` replaces `resources.completion_service`. `TypedMessageDispatcher` is removed.
2. `LlmAddon` builds `resources.llm` (`LLM_ENABLED`); `LLMInstance.astream`; `LlmCompletionHandler`; completions uses it when `resources.llm` exists, echo otherwise.
3. Observation moves into `LLMInstance` (`LlmObservation`, `LlmSink`); `CompletionService` keeps guards and stream deadlines only. **BREAKING** (only when `LLM_ENABLED=false`): the echo handler no longer produces a `completion …` log line.
4. Named `Upstream` HTTP clients with retry, circuit breaker and request-id, opened by bootstrap, read with `resources.http(name)`.
5. One DB access pattern (store takes `sessionmaker` / `MongoGateway`); `DbSession`, `get_db`, `MongoDep`, `get_mongo`, `get_mongo_gateway` removed. Sample domain `conversations` (Postgres) behind `CONVERSATIONS_ENABLED`.
6. Optional route helpers `require_quota(...)` and `@idempotent`; no route enables them by default.

## Impact

- HTTP contract of `/api/v1/completions*` is unchanged in every step.
- Python API break: `create_app(completion_handler_factory=, completion_guards_factory=)` becomes `create_app(features=)`; same for `worker_context`.
- Settings added: `LLM_ENABLED`, `CONVERSATIONS_ENABLED` (both default false, added to `.env.example`).
- New migration `0010_create_conversations`.
- Docs: `docs/agents/architecture.md`, `docs/agents/ai-engineering.md`, `docs/template-guide.md`, `docs/usage.md`, `README.md`.
