# Architecture

Where code lives and how it is wired. This repo is a template, not a plugin platform: new apps clone it and wire their own product services.

## Layers

| Path | Role |
| --- | --- |
| `app/api` | Transport/controller layer. |
| `app/bootstrap` | App factory, lifespan resources, central service composition. |
| `app/modules/platform` | Reusable capabilities: Mongo, quota, cache, objects, rate limit, idempotency, identity, model_server. |
| `app/modules/messaging` | Queue gateway/worker, outbox, tasks, webhooks. |
| `app/modules/ai` | Optional AI extras (LLM, RAG, evals) behind lazy-import guards (`app/modules/ai/_deps.py`). |
| `app/modules/business` | Domain/product logic only. |
| `app/core` | Settings, infra primitives, health, errors, middleware. |

Layer flow:

- API routers parse HTTP input and call a business service.
- Business services receive explicit constructor dependencies.
- Platform modules expose reusable capabilities and backend factories.
- Bootstrap opens platform resources and composes app services.

Prefer existing repo patterns over new abstractions.

### API (`app/api`)

- Owns route paths, request parsing, query/path/body parameters, response models/envelopes, auth dependencies.
- Calls one business service method per endpoint when possible.
- Preserves legacy contracts during migration: path, method, query names, body shape, envelope, status behavior.
- Views read services from `get_app_resources(request.app)` (the deliberate `app.state` seam). Feature-gated groups use one typed accessor in `app/bootstrap/state.py` (e.g. `get_task_services`).
- Endpoint files never build stores, DB clients, HTTP clients, quota adapters, LLMs or generators, and never hold business workflow decisions.
- No generic `app/api/deps.py` that collects unrelated wiring.

### Bootstrap (`app/bootstrap`)

- Opens lifecycle-owned platform resources, composes application services from them, stores each composed business service on its typed `ApplicationResources` field (one instance per app), and closes resources in reverse order.
- Use it for app-lifetime dependencies: shared HTTP clients, LLM instances, Mongo gateway, quota service, task service, cache, object storage, webhook dispatcher.
- Anchors:
  - `resources.py`: `ApplicationResources`, open/close lifecycle.
  - `addons.py`: `BootstrapAddon` protocol and default addon order.
  - `state.py`: typed helpers such as `get_app_resources(...)`, `get_task_services(...)`.
  - `services.py`: `compose_business_services`, handler factories.
  - `addons/<name>.py`: one addon per capability. Contract (`addons/base.py`): `open(resources, settings, stack)` builds the capability with factory functions that take required dependencies, stores it on `resources`, and pushes its close onto `stack`. No `close` method.
- Cross-setting rules ("X requires Y") live in a `@model_validator` on the owning settings mixin, not in addons or factories.

### Platform modules (`app/modules/platform`)

- Reusable cross-product capabilities and backend adapters; factories choose concrete backends from settings; each adapter implements one backend.
- Examples: quota service over memory/postgres/mongo stores; Mongo gateway; cache, objects, idempotency, rate limit, identity.
- No product-specific setup here.

```text
factory chooses implementation
adapter implements one stack
service consumes interface/capability
```

### Business modules (`app/modules/business`)

- Domain/product services, schemas, models, stores, integrations, generation logic.
- Services receive explicit constructor dependencies. Stores own collection/table details; integrations own external API details; AI generation owns prompt building and model parsing.
- A business service never reads `Request` or `app.state`, never uses a global service locator, and never opens app-lifetime runtime resources itself.

### Package `__init__.py`

`__init__.py` files stay empty (a docstring is allowed); no re-exports, no `__all__`. Import each symbol from the file that defines it, and only what you use. `tests/unit/test_package_inits.py` enforces this.

## Adding or changing a service

1. Define one `<Domain>Service` class in `app/modules/business/<domain>/service.py` (e.g. `CompletionService`); add schemas/types/models/stores/integrations under the same domain.
2. Keep stores, handlers and external integrations as constructor dependencies.
3. Decide scope: request-scoped uses an existing FastAPI dependency or session boundary; app-lifetime is built once per app in lifespan after resources open (`app/bootstrap/services.py`) and stored on a typed `ApplicationResources` field (e.g. `completion_service: CompletionService`). No module-level singletons.
4. A feature behind a `*_ENABLED` flag gets a feature group (e.g. `TaskServices`) that exists only when enabled; `app/api/router.py` mounts its router only when enabled; one typed accessor in `app/bootstrap/state.py` (e.g. `get_task_services`) resolves it.
5. Endpoint functions read the service from `get_app_resources(request.app)`, parse HTTP input, call one service method, and return the existing response contract. No per-surface getter helpers.
6. Tests: unit test for orchestration and failure modes; bootstrap test that lifespan composes the service; integration test for the API contract (tests run the app lifespan, see `tests/factories.py:api_client_for`).

## Adding an endpoint

```text
API endpoint
  -> dependency adapter retrieves service
  -> service.method(...)
  -> response
```

Leave bootstrap alone when the service already has its dependencies. Touch bootstrap only when the endpoint introduces a new app-level service or a new lifecycle-owned runtime dependency.

## Legacy/DGL migration

Keep legacy transport contracts stable; improve internals only:

```text
legacy endpoint path stays the same
  -> API calls service
  -> service owns business flow
  -> platform capabilities provide shared infrastructure
```

Keep legacy endpoints off the template `/api/v1/completions` pattern unless a new endpoint is requested. The completions surface is a scaffold pattern, not a replacement for migrated legacy contracts.

## Canonical Feature: completions

`app/api/v1/completions/` is the reference. For a new feature `<domain>`, copy its shape; reuse the service rules above (`<Domain>Service`, one bootstrap instance, `get_app_resources`).

- API package `app/api/v1/<domain>/`: an empty `__init__.py` and `router.py`, which declares `APIRouter(prefix=..., tags=..., dependencies=[Depends(require_principal)])` once. Every router file declares its own prefix/tags (no wrapper router in `app/api/router.py`). A feature behind a `*_ENABLED` flag adds a second file (e.g. `tasks.py`, `APIRouter(prefix="/<domain>", tags=["<domain>"])`) that `app/api/router.py` imports and mounts only when enabled; its routes take `principal: Principal = Depends(require_principal)` as a parameter when they need the id.
- View: `get_app_resources(request.app).<domain>_service`, one service call, `<Response>.model_validate(result, from_attributes=True)`. Response ids default in the response schema (`Field(default_factory=...)`). A view does not time, log, record telemetry, apply deadlines or mint ids.
- Streaming: the view passes an async generator of `ServerSentEvent` to `event_stream_response(request, events)` from `app/api/sse.py`, which owns headers, heartbeat, first-event priming (errors before it stay JSON errors), `event: error` frames and shielded close. The generator closes the service stream with `contextlib.aclosing`. A feature owns no SSE engine, heartbeat or deadline code. Frames: each non-empty delta yields `ServerSentEvent({"type": "content.delta", "delta": ..., "metadata": ...})`; the stream ends with `ServerSentEvent({"type": "done", **summary.model_dump(exclude_none=True)})`.
- Timing, deadlines, outcome labels and telemetry live in the business service, behind ports (`CompletionSink`, `StreamPolicy`) that `compose_business_services` in `app/bootstrap/services.py` builds once. The API and the worker share that instance, so both are observed.
- Task routes: the task type constant lives in the business schemas (`COMPLETION_TASK_TYPE`). Submit calls `service.submit(type=..., payload=payload.model_dump(mode="json"), principal_id=principal.id, request_id=get_request_id())` and returns `202`; reads use `require_owned(task_id, principal_id=..., type=...)`. Both responses are `TaskSubmitResponse.model_validate(task)` / `TaskResponse.model_validate(task)`.

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

## Verification

Run the narrowest useful checks, then widen:

- `uv run ruff check app tests`
- `uv run pyright`
- focused pytest for the touched module/API
- full `uv run pytest` after bootstrap, platform, or public API changes

Docker smoke checks: use a minimal local runtime with external AI dependencies disabled unless real provider calls are requested.

AI features: see `docs/agents/ai-engineering.md`.
