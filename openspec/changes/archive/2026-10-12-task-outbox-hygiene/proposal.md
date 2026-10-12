## Why

Follow-ups left by `fix-async-dispatch-path`:

1. A task that crashes its worker every time (process dies, lease expires) is
   reclaimed forever: `attempts` grows and there is no terminal state.
2. Published outbox rows are never purged, and `TaskStore.delete_expired` has no
   caller, so both tables grow without bound.
3. `ix_quota_reservations_subject_id` is a leftmost prefix of the unique index
   `uq_quota_reservations_idempotency (subject_id, resource, window_key,
   idempotency_key)` and costs writes for nothing.

## What Changes

- **Poison-task cap.** New `TASKS_MAX_ATTEMPTS` (default 5, 1..100).
  `TaskStore.reclaim_stale_processing(now, limit, max_attempts)` fails an
  expired-lease task whose `attempts >= max_attempts` (status FAILED, error
  `max_attempts_exceeded`, no lease) and requeues the others. Only requeued tasks
  are returned, so only they are announced again; `limit` bounds failed + requeued
  together. Postgres does it in the same bounded `UPDATE ... RETURNING` (a `CASE`
  on `attempts`), so with outbox dispatch the failure and the (absent) event stay
  consistent in one transaction. `max_attempts` is a call argument threaded
  through `TaskService`/`TaskDispatcher` (the service is built by bootstrap, which
  this change does not touch); the reclaim loop passes the setting.
- **Retention loop.** `run_cleanup_loop` (in `tasks/relay.py`) joins the worker's
  `TaskGroup` for every dispatch backend. Each tick it calls
  `TaskStore.delete_expired(now, limit)` and, when the outbox is enabled,
  `OutboxStore.delete_published_before(now - OUTBOX_RETENTION_SECONDS, limit)`,
  repeating each until a batch comes back short. Both deletes are
  `DELETE ... WHERE id IN (SELECT id ... LIMIT n)`. `delete_expired` gains a
  required `limit`. New settings: `OUTBOX_RETENTION_SECONDS` (7 days),
  `TASKS_CLEANUP_INTERVAL_SECONDS` (1 h), `TASKS_CLEANUP_BATCH_SIZE` (1000).
  Pending and failed outbox rows are never purged. Redis tasks expire by TTL and
  report 0 deleted.
- **Index.** Migration `0006_drop_quota_resv_idx` drops
  `ix_quota_reservations_subject_id` (downgrade recreates it); the model no
  longer declares it.

## Capabilities

### Modified Capabilities

- `messaging/tasks`: reclaim terminal state for exhausted tasks; retention.

## Impact

- Code: `app/modules/messaging/tasks/**`, `app/modules/messaging/outbox/{adapters,store}.py`,
  `app/bootstrap/worker.py`, `app/core/config/messaging.py`, `.env.example`,
  `app/modules/platform/quota/records.py`, `alembic/versions/0006_*`.
- Behavior: `reclaim_stale_processing` and `TaskService.reclaim_stale_processing`
  require `max_attempts`; `TaskStore.delete_expired` requires `limit`; the worker
  runs one more loop.
- Not done: idempotency-key retention (`idempotency` `delete_expired` is still
  unscheduled; separate area). The outbox status index is not changed for the
  purge (the subselect filters `status = 'published'` through
  `ix_outbox_events_status_available_at`).
