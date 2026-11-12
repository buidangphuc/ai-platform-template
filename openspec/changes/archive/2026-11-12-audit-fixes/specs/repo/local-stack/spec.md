## ADDED Requirements

### Requirement: The local stack starts usable

`ops/compose/local.yaml` SHALL run `alembic upgrade head` in a one-shot service that the API and the worker wait for, SHALL publish the API port on loopback only, and SHALL use one image name shared with `make docker-build`. It SHALL NOT set `TASKS_DISPATCH_BACKEND` or the outbox relay settings.

#### Scenario: Fresh volumes
- **WHEN** `make docker-run` starts on empty volumes
- **THEN** migrations complete before the API and worker start

#### Scenario: Compose files are valid
- **WHEN** `docker compose -f ops/compose/local.yaml config` and the same with the Langfuse overlay run
- **THEN** both exit 0

### Requirement: The Langfuse overlay can trace

With the Langfuse overlay the application image SHALL be built with the `ai` extra, and the docs SHALL state which settings make the stack produce a trace.

#### Scenario: Overlay build
- **WHEN** the overlay is applied
- **THEN** the API and worker build args include `UV_EXTRAS=ai`
