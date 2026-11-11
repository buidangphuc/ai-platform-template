## ADDED Requirements

### Requirement: A feature is declared in one place

A `Feature` (`app/bootstrap/features/base.py`) SHALL declare `name`, `service` type, `build(resources, settings)`, `routers`, `task_routers`, `tasks` (task type to handler), `models` (ORM module paths), `upstreams` and `enabled(settings)`. `app/bootstrap/features/registry.py` SHALL expose `FEATURES`, and adding a domain SHALL require only its own files plus one entry there.

#### Scenario: Second feature needs no shared-file edits
- **WHEN** a test registers a second feature with a router, a service and a task handler
- **THEN** its route is mounted, `resources.service(Cls)` returns its service, and a task of its type is processed, without any change to `resources.py`, `services.py`, `worker.py`, `api/router.py` or `alembic/env.py`

#### Scenario: Disabled feature
- **WHEN** `enabled(settings)` is false
- **THEN** its routers are not mounted, `build` is not called, and `resources.service(Cls)` raises `ServiceUnavailableError`

#### Scenario: Task routers follow TASKS_ENABLED
- **WHEN** `TASKS_ENABLED` is false
- **THEN** a feature's `task_routers` are not mounted

### Requirement: API and worker share the registry

`create_app(features=FEATURES)` and `worker_context(features=FEATURES)` SHALL be the only way features reach the runtime; neither SHALL accept a domain-named factory parameter. `scripts/run_worker.py` and `main.py` SHALL use the default registry so both processes run the same handlers.

#### Scenario: Worker runs the registered handler
- **WHEN** a feature registers a task handler and the worker receives a task of that type
- **THEN** the handler runs and the task is marked completed with the handler's result

### Requirement: Worker dispatches by task type

The worker SHALL look up the handler by `task.type`. An unknown type SHALL mark the task failed and raise `NonRetryableMessageError`. Two features registering the same task type, or the same service type, SHALL fail at startup.

#### Scenario: Unknown task type
- **WHEN** the worker receives a task whose type no feature registers
- **THEN** the task is failed and the message is dead-lettered without retry

#### Scenario: Duplicate task type
- **WHEN** two enabled features register the task type `x`
- **THEN** opening the runtime raises an error naming `x` and both features

### Requirement: Alembic sees feature models

`alembic/env.py` SHALL import every module listed in `models` of the registered features, so autogenerate cannot miss a table.

#### Scenario: Feature declares a model module
- **WHEN** a feature lists `app.modules.business.conversations.models`
- **THEN** its tables are in `Base.metadata` when alembic loads

### Requirement: Completions is a registered feature

Completions SHALL be `completions_feature(handler_factory, guards_factory)` in `app/bootstrap/features/completions.py`. Its service SHALL be read with `get_app_resources(request.app).service(CompletionService)`, and `ApplicationResources.completion_service` SHALL NOT exist. `/api/v1/completions`, `/stream` and `/tasks` SHALL behave exactly as before.

#### Scenario: Contract unchanged
- **WHEN** the existing completions integration tests run
- **THEN** they pass without changes to their assertions
