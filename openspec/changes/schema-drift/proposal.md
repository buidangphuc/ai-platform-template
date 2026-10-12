## Why

`alembic check` reported drift between ORM models and migrations, so the CI `migrations` job was advisory. Indexes and server defaults existed only in migrations, four indexes duplicated the leftmost prefix of another index, status columns accepted any string, and stale-task reclaim had no supporting index.

## What Changes

- Declare the migration-only indexes (`tasks`, `outbox_events`) and `server_default`s (`tasks.status`, `tasks.attempts`, `outbox_events.attempts`, `audit_events.metadata`) on the models.
- New migration `0005_schema_drift_cleanup`: drop `ix_tasks_status`, `ix_outbox_events_status`, `ix_idempotency_keys_principal_id`, `ix_quota_counters_subject_id` (prefixes of composite/unique indexes); add CHECK constraints on task, outbox, idempotency and quota reservation status plus `quota_counters.used >= 0`; add partial index `ix_tasks_processing_locked_until` (`WHERE status = 'processing'`). Downgrade reverses all of it.
- Remove `continue-on-error` from the CI `alembic check` step.

## Capabilities

None (schema only; no behavior change for valid data).

## Impact

Existing rows with out-of-enum status values or negative `used` would fail the upgrade. Column names and types are unchanged.
