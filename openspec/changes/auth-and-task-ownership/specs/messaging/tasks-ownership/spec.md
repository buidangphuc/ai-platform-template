## ADDED Requirements

### Requirement: Tasks are owned by their submitter

Each task SHALL record the `principal_id` that submitted it, supplied explicitly
to `TaskService.submit`. API reads SHALL return a task only to its owner; for any
other principal the response SHALL be 404 `task_not_found`, identical to a missing
task. Worker reads SHALL NOT filter by owner. Every task store adapter and the
Postgres task+outbox insert SHALL persist and filter by `principal_id`. Rows that
predate ownership SHALL have an empty owner and SHALL NOT be returned by API reads.

#### Scenario: Another principal polls a task
- **WHEN** principal `mallory` requests `GET /completions/tasks/{id}` for a task submitted by `alice`
- **THEN** the response is 404 `task_not_found`

#### Scenario: Owner polls through a rotated key
- **WHEN** `alice` polls with a second key of the same subject
- **THEN** the task is returned

#### Scenario: Worker reads any task
- **WHEN** the worker loads a task by id without a principal
- **THEN** it receives the task regardless of owner
