# messaging/tasks-tracing-reclaim Specification

## Purpose
Keeping worker logs correlated with the submitting request across crash recovery.

## Requirements

### Requirement: The task persists its submitting request id

The task store SHALL persist the request id given at submit on the task, in every
backend, and a reclaim that requeues a task SHALL return it so the dispatcher
re-announces the task with that request id. A task submitted without one, or one
created before the column existed, is re-announced without a `request_id`.

#### Scenario: Reclaim after a worker crash
- **GIVEN** a task submitted with `request_id="req_abc"` whose processing lease expired
- **WHEN** the reclaim loop requeues it
- **THEN** the re-announced message body contains `"request_id": "req_abc"`, whether the dispatcher is the direct queue or the Postgres outbox

#### Scenario: Task without a request id
- **WHEN** a task submitted without a request id is reclaimed
- **THEN** the re-announced message body has no `request_id` key

#### Scenario: Persisted in every backend
- **WHEN** a task with a request id is stored in the memory, Redis or Postgres store
- **THEN** `get` returns the same request id
