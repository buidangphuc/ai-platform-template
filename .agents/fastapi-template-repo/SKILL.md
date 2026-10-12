---
name: fastapi-template-repo
description: Understand and modify this FastAPI template repository with a codegraph-first workflow. Use for repo architecture questions, adding endpoints or business services, migrating legacy/DGL code, reviewing dependency wiring, debugging request-to-service flows, or any task that asks how this backend is structured.
---

# FastAPI Template Repo

This repo-local agent skill is the canonical AI instruction for this backend.
Agents should read it through the repo instructions in `AGENTS.md` and
`CLAUDE.md`.

## Core Workflow

1. Start with `mcp__codegraph.codegraph_context` for architecture, flow, bug, or feature tasks when the tool is available.
2. If codegraph reports stale entries or misses the target, verify with `rg` and direct file reads.
3. Keep the layer boundary visible before editing:
   - API routers parse HTTP input and call a business service.
   - Business services receive explicit constructor dependencies.
   - Platform modules expose reusable capabilities and backend factories.
   - Bootstrap opens platform resources and composes app services.
4. Prefer the repo's existing patterns over new abstractions.
5. Verify with focused tests first, then broader checks when bootstrap, platform, or API contracts change.

## Codegraph Usage

Use codegraph as the first map, not the only source of truth.

- Use `codegraph_context` for "how does this work?", "where should this go?", endpoint flow, service wiring, and bug reports.
- Use `codegraph_trace` when the user asks how one symbol reaches another.
- Use `codegraph_search` only for quick symbol discovery.
- If the response says files are stale or pending sync, inspect those exact files with `rg`, `sed`, or `nl` before deciding.
- Do not re-read files already fully included by codegraph unless you need fresher content or surrounding lines.
- If the current agent does not have codegraph tools, fall back to `rg`, `sed`, `nl`, and focused tests.

## Repository Rules

Load `references/architecture.md` when adding services/endpoints, changing bootstrap wiring, reviewing platform-vs-business boundaries, or migrating legacy code.

Short version:

- `app/api`: transport/controller layer.
- `app/bootstrap`: app factory, lifespan resources, and central service composition.
- `app/modules/platform`: reusable capabilities such as Mongo, quota, cache, objects, rate limit, idempotency, model_server.
- `app/modules/messaging`: queue gateway/worker, outbox, tasks, webhooks.
- `app/modules/ai`: optional AI extras (LLM, RAG, evals) behind lazy-import guards (`app/modules/ai/_deps.py`).
- `app/modules/business`: domain/product logic only.
- `app/core`: settings, infra primitives, health, errors, middleware.

Avoid:

- Business services reading `Request`, `app.state`, or global service locators.
- Endpoint files constructing stores, HTTP clients, LLMs, quota stores, or dependency graphs.
- Product-specific setup inside `app/modules/platform`.
- Generic `deps.py` files that collect unrelated feature wiring.
- Re-exports in `__init__.py` and `__all__`. Package `__init__.py` files stay empty (a docstring is allowed);
  import each symbol from the file that defines it, and only what you use. `tests/unit/test_package_inits.py`
  enforces this.

## Adding Or Changing A Service

Use this sequence:

1. Define one `<Domain>Service` class in `app/modules/business/<domain>/service.py` (e.g. `CompletionService`).
2. Keep stores, handlers and external integrations as constructor dependencies.
3. Bootstrap builds exactly one instance per app, in lifespan after resources open
   (`app/bootstrap/services.py`), and stores it on a typed field of `ApplicationResources`
   (e.g. `completion_service: CompletionService`). No module-level singletons.
4. A feature behind a `*_ENABLED` flag gets a feature group (e.g. `TaskServices`) that exists only
   when enabled; `app/api/router.py` mounts its router only when enabled, and one typed accessor in
   `app/bootstrap/state.py` (e.g. `get_task_services`) resolves it.
5. Endpoint functions read the service from `get_app_resources(request.app)`, parse HTTP input, call
   one service method, and return the existing response contract. No per-surface getter helpers.
6. Add unit tests for service behavior and integration tests for API contract (tests run the app lifespan,
   see `tests/factories.py:api_client_for`).

Adding a new endpoint usually should not touch bootstrap. Touch bootstrap only when the endpoint introduces a new app-level service or a new lifecycle-owned runtime dependency.

## Canonical Feature: completions

`app/api/v1/completions/` is the reference. For a new feature `<domain>`, copy its shape; reuse the
service rules above (`<Domain>Service`, one bootstrap instance, `get_app_resources`).

- API package `app/api/v1/<domain>/`: an empty `__init__.py` and `router.py`, which declares
  `APIRouter(prefix=..., tags=..., dependencies=[Depends(require_principal)])` once. A feature behind a
  `*_ENABLED` flag adds a second file (e.g. `tasks.py`) with a plain `APIRouter()`, mounted in
  `app/api/router.py` only when enabled; its routes take `principal: Principal = Depends(require_principal)`
  as a parameter when they need the id.
- View: `get_app_resources(request.app).<domain>_service`, one service call,
  `<Response>.model_validate(result, from_attributes=True)`. Response ids default in the response schema
  (`Field(default_factory=...)`). A view does not time, log, record telemetry, apply deadlines or mint ids.
- Streaming: the view passes an async generator of `ServerSentEvent` to `event_stream_response(request, events)`
  from `app/api/sse.py`, which owns headers, heartbeat, first-event priming (errors before it stay JSON
  errors), `event: error` frames and shielded close. The generator closes the service stream with
  `contextlib.aclosing`. A feature owns no SSE engine, heartbeat or deadline code.
- Timing, deadlines, outcome labels and telemetry live in the business service, behind ports
  (`CompletionSink`, `StreamPolicy`) that `compose_business_services` in `app/bootstrap/services.py`
  builds once. The API and the worker share that instance, so both are observed.
- Task routes: the task type constant lives in the business schemas (`COMPLETION_TASK_TYPE`); reads use
  `require_owned(task_id, principal_id=..., type=...)`; responses use `TaskResponse.model_validate(task)`.

Reference views (`app/api/v1/completions/router.py`):

```python
@router.post("", response_model=CompletionResponse)
async def complete(payload: CompletionRequest, request: Request) -> CompletionResponse:
    service = get_app_resources(request.app).completion_service
    result = await service.complete(payload)
    return CompletionResponse.model_validate(result, from_attributes=True)


@router.post("/stream")
async def stream(payload: CompletionRequest, request: Request) -> StreamingResponse:
    service = get_app_resources(request.app).completion_service
    return await event_stream_response(request, _events(service.stream(payload)))
```

## Verification Defaults

Run the narrowest useful checks, then widen:

- `uv run ruff check app tests`
- `uv run pyright`
- focused pytest for touched module/API
- full `uv run pytest` after bootstrap, platform, or public API changes

For Docker smoke checks, prefer a minimal local runtime with disabled external AI dependencies unless the user explicitly wants real provider calls.
