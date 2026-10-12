## Why

Two gaps left by `idempotency-correctness`:

1. Completion was fenced on `request_hash` and `status` only, so a late original
   whose request is byte-identical to the reclaiming retry could still complete
   the retry's claim.
2. `delete_expired` had no caller, so `idempotency_keys` grew without bound.

## What Changes

- **Claim token.** New nullable `idempotency_keys.claim_token` (uuid string),
  set to a fresh value on every claim and reclaim. `check_or_store` returns
  `IdempotencyCachedResponse | IdempotencyClaim` (the claim carries the token;
  it no longer returns `None`). `store_response` takes `claim_token` instead of
  `request_hash` and fences with `WHERE claim_token = :t AND status = 'in_progress'`.
  `IdempotentCall` carries the token instead of the hash. Rows claimed before
  the migration have a NULL token: they can only expire or be reclaimed.
- **Retention.** `delete_expired(before, limit)` takes a required `limit` and
  deletes with `DELETE ... WHERE id IN (SELECT id ... LIMIT n)`. The worker's
  `run_cleanup_loop` also drains it in batches when `resources.idempotency_store`
  exists. New index `ix_idempotency_keys_expires_at` keeps the purge subselect
  off a full scan.
- Migration `0007_idempotency_claim_token` (down_revision
  `0006_drop_quota_resv_idx`): add column and index; downgrade drops both.

## Capabilities

### Modified Capabilities
- `platform/idempotency`: token-fenced completion; retention.

## Impact

- Code: `app/modules/platform/idempotency/**`, `app/modules/messaging/tasks/relay.py`
  (`run_cleanup_loop` gains an `idempotency_store` argument),
  `app/bootstrap/worker.py` (cleanup wiring), `alembic/versions/0007_*`.
- **BREAKING (store API)**: `check_or_store` return type, `store_response`
  parameter, `delete_expired` required `limit`. No endpoint uses idempotency yet.
- Not done: no heartbeat (handlers outliving the in-progress timeout can still
  be re-run); raise the timeout instead.
