## Why

A task reclaimed after a worker crash was re-announced without its request id, so
the worker logged `req=-` for the retry. Found in a live compose run: the id only
travelled on the queue message of the first announcement, never on the task, so
reclaim (queue and Postgres outbox dispatchers alike) had nothing to re-announce
with.

## What Changes

- `TaskRecord.request_id: str | None` and `TaskRef.request_id: str | None`.
  `TaskService.submit` stores the request id on the task.
- `TaskDispatcher.submit(task)` no longer takes a `request_id` argument: the task
  carries it. Both dispatchers announce `task.request_id` on submit and
  `ref.request_id` on reclaim.
- Every store adapter persists it: Postgres `tasks.request_id` (nullable
  `String(255)`, migration `0009_task_request_id`, no backfill), Redis JSON field,
  in-memory field. Postgres reclaim `RETURNING` includes it.

## Capabilities

### New Capabilities

- `messaging/tasks-tracing-reclaim`: the request id survives a reclaim.

### Modified Capabilities

None archived yet. This change overrides one scenario of
`messaging/tasks-tracing` (change `streaming-observability`, "Message without a
request id": a reclaimed task now carries its id).

## Impact

- Code: `app/modules/messaging/tasks/**`, `alembic/versions/0009_task_request_id.py`.
- Migration is additive and nullable; rows created before it are re-announced
  without a request id, as before.
