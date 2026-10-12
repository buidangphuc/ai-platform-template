# api/completions Specification

## Purpose
How the completions API surface obtains its business service and which routes are exposed.

## Requirements

### Requirement: Completion service is composed once from opened resources

The application SHALL build exactly one completion business service per app, during lifespan startup
after platform resources are open, by calling the configured completion handler factory with those
resources and settings.

#### Scenario: Handler factory receives opened resources
- **WHEN** the app starts with a custom completion handler factory
- **THEN** the factory is called once with the application's opened resources
- **AND** completion requests are served by the handler it returned

#### Scenario: Default handler answers without configuration
- **WHEN** the app starts without a custom completion handler factory
- **THEN** `POST /api/v1/completions` returns 200 from the scaffold echo handler

### Requirement: Task routes exist only when tasks are enabled

The application SHALL mount the async completion task routes only when `TASKS_ENABLED` is true.

#### Scenario: Tasks disabled
- **WHEN** `TASKS_ENABLED` is false
- **THEN** `POST /api/v1/completions/tasks` returns 404

#### Scenario: Tasks enabled
- **WHEN** `TASKS_ENABLED` is true
- **THEN** `POST /api/v1/completions/tasks` returns 202 with a task id
