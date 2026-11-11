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
- Views read services from `get_app_resources(request.app)` (the deliberate `app.state` seam). Feature-gated groups use one typed accessor in `app/bootstrap/state.py` (e.g. `get_task_services`).
- Endpoint files never build stores, DB clients, HTTP clients, quota adapters, LLMs or generators, and never hold business workflow decisions.
- No generic `app/api/deps.py` that collects unrelated wiring.

### Bootstrap (`app/bootstrap`)

- Opens lifecycle-owned platform resources, composes application services from them, stores each composed business service on its typed `ApplicationResources` field (one instance per app), and closes resources in reverse order.
- Use it for app-lifetime dependencies: shared HTTP clients, LLM instances, Mongo gateway, quota service, task service, cache, object storage, webhook dispatcher.
- Anchors:
  - `resources.py`: `ApplicationResources`, open/close lifecycle.
  - `addons/base.py`: `BootstrapAddon` protocol and default addon order.
  - `state.py`: typed helpers such as `get_app_resources(...)`, `get_task_services(...)`.
  - `features/base.py`: the `Feature` declaration. `features/registry.py`: `FEATURES`, the one list `create_app(features=FEATURES)` and `worker_context(features=FEATURES)` read. `features/<domain>.py`: one file per domain (e.g. `completions.py`).
  - `services.py`: `compose_business_services`, `open_runtime`; builds each enabled feature's service and rejects duplicate service or task types at startup.
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
3. Declare the domain once: `app/bootstrap/features/<domain>.py` returns a `Feature` (`name`, `service`, `build(resources, settings)`, `routers`, `task_routers`, `tasks`, `models`, `upstreams`, `enabled(settings)`), and `app/bootstrap/features/registry.py` gets one entry in `FEATURES`. That is the only shared-file edit: `resources.py`, `services.py`, `api/router.py`, `worker.py` and `alembic/env.py` read the registry.
4. Scope: the service is built once per app in lifespan after resources open (`Feature.build`) and stored on `resources.services`; read it with `resources.service(<Domain>Service)`, which raises `ServiceUnavailableError` when the feature is disabled. No module-level singletons.
5. A feature behind a `*_ENABLED` flag sets `enabled=lambda settings: settings.<DOMAIN>_ENABLED`: a disabled feature is not built, not mounted and not resolvable. Routes that need `TASKS_ENABLED` go in `task_routers`. A platform capability behind a flag still gets a feature group (e.g. `TaskServices`) and one typed accessor in `app/bootstrap/state.py` (e.g. `get_task_services`).
6. Background tasks: `tasks={TASK_TYPE: handler}` with `handler(resources, task) -> dict`; the worker dispatches by `task.type`. An unknown type fails the task and dead-letters the message; two features registering the same task type or service type fail at startup.
7. ORM tables: list the model modules in `models=(...)`; `alembic/env.py` imports them.
8. Endpoint functions read the service from `get_app_resources(request.app).service(<Domain>Service)`, parse HTTP input, call one service method, and return the existing response contract. No per-surface getter helpers.
9. Tests: unit test for orchestration and failure modes; bootstrap test that lifespan composes the service (`tests/unit/core/test_features.py` shows a second feature); integration test for the API contract (tests run the app lifespan, see `tests/factories.py:api_client_for`; build the app with `create_app(features=(<domain>_feature(...),))`).

## Calling external HTTP APIs

Declare an `Upstream(name, base_url, timeout, retries, headers, follow_redirects)` in the feature's `upstreams` (`app/modules/platform/http/upstream.py`) and call it with `resources.http(name)`, an `UpstreamClient` (`get`, `post`, `request`). Bootstrap opens one `httpx.AsyncClient` per upstream of every enabled feature and closes it on shutdown; each call applies the timeout, retries transient failures up to `retries`, trips a per-upstream circuit breaker (`ServiceUnavailableError`, code `upstream_unavailable`), sends `X-Request-ID` and logs one line without bodies or headers. Two enabled features declaring the same upstream name fail at startup; an unknown name raises `upstream_not_configured`. `retries` applies to every method including POST, so enable it only for idempotent calls. Do not build an `httpx.AsyncClient` in a feature or service.

In integration or worker tests, mock the upstream with `mock_upstreams` from `tests/factories.py` (named upstreams use an `httpx.MockTransport`; other names keep the real transport):

```python
def test_lookup(monkeypatch):
    mock_upstreams(monkeypatch, {"geo": lambda request: httpx.Response(200, json={"city": "x"})})
    # then create_app(...) / worker_context(...) as usual; resources.http("geo") hits the handler
```

## Adding an endpoint

```text
API endpoint
  -> dependency adapter retrieves service
  -> service.method(...)
  -> response
```

Leave bootstrap alone when the service already has its dependencies. Touch bootstrap only when the endpoint introduces a new app-level service or a new lifecycle-owned runtime dependency.

## Canonical Feature: completions

`app/api/v1/completions/` and `app/bootstrap/features/completions.py` are the reference. For a new feature `<domain>`, copy their shape; reuse the service rules above (`<Domain>Service`, one `Feature` entry in `FEATURES`, `get_app_resources`). Products pass their handler to `completions_feature(handler_factory=..., guards_factory=...)`.

- API package `app/api/v1/<domain>/`: an empty `__init__.py` and `router.py`, which declares `APIRouter(prefix=..., tags=..., dependencies=[Depends(require_principal)])` once. Every router file declares its own prefix/tags (no wrapper router in `app/api/router.py`). A feature behind a `*_ENABLED` flag adds a second file (e.g. `tasks.py`, `APIRouter(prefix="/<domain>", tags=["<domain>"])`) that the feature lists in `task_routers`; it is mounted only when `TASKS_ENABLED`, and its routes take `principal: Principal = Depends(require_principal)` as a parameter when they need the id.
- View: `get_app_resources(request.app).service(<Domain>Service)`, one service call, `<Response>.model_validate(result, from_attributes=True)`. Response ids default in the response schema (`Field(default_factory=...)`). A view does not time, log, record telemetry, apply deadlines or mint ids.
- Streaming: the view passes an async generator of `ServerSentEvent` to `event_stream_response(request, events)` from `app/api/sse.py`, which owns headers, heartbeat, first-event priming (errors before it stay JSON errors), `event: error` frames and shielded close. The generator closes the service stream with `contextlib.aclosing`. A feature owns no SSE engine, heartbeat or deadline code. Frames: each non-empty delta yields `ServerSentEvent({"type": "content.delta", "delta": ..., "metadata": ...})`; the stream ends with `ServerSentEvent({"type": "done", **summary.model_dump(exclude_none=True)})`.
- Timing, outcome labels and telemetry live in `LLMInstance` (one `LlmObservation` per model call, reported to an `LlmSink` composed by `LlmAddon`); the business service keeps guards and `StreamPolicy` deadlines. `completions_feature(...).build` in `app/bootstrap/features/completions.py` builds the service once; the API and the worker share it, so both are observed.
- Task routes: the task type constant lives in the business schemas (`COMPLETION_TASK_TYPE`) and is registered in the feature's `tasks` (the worker runs that handler; the worker module knows no domain). Submit calls `service.submit(type=..., payload=payload.model_dump(mode="json"), principal_id=principal.id, request_id=get_request_id())` and returns `202`; reads use `require_owned(task_id, principal_id=..., type=...)`. Both responses are `TaskSubmitResponse.model_validate(task)` / `TaskResponse.model_validate(task)`.

Reference views (`app/api/v1/completions/router.py`):

```python
@router.post("", response_model=CompletionResponse)
async def complete(payload: CompletionRequest, request: Request) -> CompletionResponse:
    service = get_app_resources(request.app).service(CompletionService)
    result = await service.complete(payload)
    return CompletionResponse.model_validate(result, from_attributes=True)


@router.post("/stream")
async def stream(payload: CompletionRequest, request: Request) -> StreamingResponse:
    service = get_app_resources(request.app).service(CompletionService)
    return await event_stream_response(request, _events(service.stream(payload)))
```

## Verification

The canonical check list is `## Checks` in `docs/agents/project.md`; CI mirrors it. Run the narrowest useful check first (focused pytest for the touched module/API), then widen to the full list after bootstrap, platform, or public API changes.

### Testing a feature

- Integration: `create_app(settings=build_test_settings(...))` with the feature's flags flipped (default registry), or `create_app(features=(<domain>_feature(...),))` for a custom handler. `init_resources` defaults to True; the lifespan opens addons either way.
- Worker: settings `QUEUE_ENABLED=True, TASKS_ENABLED=True, QUEUE_BACKEND="memory", TASK_STORE_BACKEND="memory"`, then `worker_context(settings, features=...)`: `ctx.tasks.service.submit(...)`, `[message] = await ctx.tasks.queue.receive(max_messages=1)`, `await ctx.worker.handler(message)`. `tests/unit/core/test_features.py` is the working example.
- Upstreams: `mock_upstreams` (see "Calling external HTTP APIs"). LLM: `model_builder` (see `docs/agents/ai-engineering.md`).

Docker smoke checks: use a minimal local runtime with external AI dependencies disabled unless real provider calls are requested.

AI features: see `docs/agents/ai-engineering.md`.
