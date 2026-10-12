## Why

The audit of the quota platform module found correctness bugs in the Postgres and Mongo stores: a double refund under concurrent calls (Mongo counter can go negative), duplicate or 500-ing reservations for the same idempotency key, lost updates when migrating active counters, naive datetimes read back from Mongo (TypeError after the first window rollover), no Mongo indexes, a Postgres upsert that never updated `updated_at` (and referenced a non-existent `limit` column), and `alembic/env.py` not importing the quota models (autogenerate would drop the quota tables).

## What Changes

- Mongo client is built with `tz_aware=True, tzinfo=UTC` so stored datetimes compare with `datetime.now(UTC)`.
- `MongoQuotaStore.ensure_indexes()` (idempotent): unique counter key, unique partial reservation idempotency key, TTL on `reset_at` (24h grace).
- Mongo reserve inserts the reservation and, on `DuplicateKeyError`, gives back the counter charge and returns the existing reservation.
- Mongo counter migration claims each stale counter atomically (`find_one_and_delete`) and moves its usage with `$inc` instead of read-modify-write.
- Refund/finalize are a single conditional write (`status = 'reserved'` guard) in both stores; the counter is decremented only by the caller that won the transition.
- Postgres reserve uses `INSERT ... ON CONFLICT DO NOTHING RETURNING` and returns the existing reservation on conflict (no 500, no counter leak); an over-limit reserve removes its provisional row.
- Postgres counter upsert sets `updated_at` and uses the real column name `quota_limit`.
- `alembic/env.py` imports `app.modules.platform.quota.records`.

## Capabilities

### New Capabilities
- `platform/quota`: externally visible guarantees of the quota stores (exactly-once refund/finalize, idempotent reserve, timezone-aware timestamps).

### Modified Capabilities
None.

## Impact

- Code: `app/core/mongo.py`, `app/modules/platform/quota/adapters/{mongo,postgres}.py`, `alembic/env.py`; new tests under `tests/unit/modules/`.
- Mongo deployments gain indexes once `ensure_indexes()` runs. Existing duplicate counters/reservations must be cleaned up before the unique indexes can be built.
- No API or schema changes for Postgres.

## Follow-ups

- TODO: Wave 2 bootstrap calls `MongoQuotaStore.ensure_indexes` at open (factory/bootstrap are owned by another packet).
- The counter migration is claim-then-increment: a crash between the two steps drops the migrated usage (under-counts, never over-charges).
