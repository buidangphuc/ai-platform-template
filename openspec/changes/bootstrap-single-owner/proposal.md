## Why

The audit found that bootstrap is not the single owner of infrastructure:
- The completion handler is built before lifespan opens resources, so a real handler cannot take
  the LLM, RAG or stores it needs.
- The API answers 501 while the worker silently runs the echo handler.
- Addon lifecycle code lives in platform factories.
- The worker re-implements resource opening.
- Optional fields force the same "is it there?" check at several layers.

Findings: B1–B11 and the defensive-check pass in the master audit plan.

## What Changes

Step 1 (this commit):
- `CompletionPipeline` is renamed `CompletionService` (`business/completions/service.py`). It is built
  exactly once per app, in lifespan, by `app/bootstrap/services.py:compose_business_services` from a
  `completion_handler_factory(resources, settings)`, and stored on the typed field
  `ApplicationResources.completion_service`.
- **BREAKING:** `create_app(completion_handler=...)` becomes
  `create_app(completion_handler_factory=...)`. The default factory returns `EchoCompletionHandler`, the
  same handler the worker already uses. **BREAKING:** the 501 `completion_handler_not_configured`
  response is gone.
- Tasks become a feature group, `TaskServices(service, store, dispatcher)`, on
  `ApplicationResources.tasks`. Its router is mounted only when `TASKS_ENABLED`; when disabled the routes
  return 404 instead of 503. One typed accessor resolves it: `bootstrap/state.py:get_task_services`.
- Removed: `app/api/v1/completions/dependencies.py`, `get_task_service`,
  `ApplicationResources.services` and `get_service_resource`. Views read
  `get_app_resources(request.app)` directly.
- Tests run the app lifespan (`tests/factories.py:api_client_for`), as production does.

Later steps (same change, tracked in tasks.md):
- One `open_core_resources`/`close` built on `AsyncExitStack` and shared by API and worker.
- Outbox store built once.
- Addon classes move into `app/bootstrap/addons/`.
- Factories take non-optional dependencies.
- Cross-setting rules move into one `Settings` validator.

## Capabilities

### New Capabilities

- `api/completions`: how the completions surface resolves its business service and which routes exist.

### Modified Capabilities

None.

## Impact

- Products that called `create_app(completion_handler=...)` must pass a factory instead.
- Clients that relied on the 501 or 503 responses now get 200 (echo) or 404.
- Skill docs, `README.md` and `TEMPLATE_GUIDE.md` are updated in the same change.
