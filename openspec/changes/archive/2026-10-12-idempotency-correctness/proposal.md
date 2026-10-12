## Why

The audit of `platform/idempotency` found that two concurrent retries of an expired or stuck key could both reclaim it and both run the handler, that a late original request could overwrite the response of the retry that reclaimed the key, that the 60s in-progress timeout was shorter than a realistic LLM call (a retry mid-call re-ran the handler), and that the HTTP helper handed state over through untyped `request.state` with a duplicated enabled check.

## What Changes

- The conflict path reads the record with `SELECT ... FOR UPDATE`, so concurrent reclaimers serialize and only the first resets the record; a reclaim refreshes `updated_at`.
- `store_idempotency_response` / `store_response` are fenced: `UPDATE ... WHERE request_hash = :h AND status = 'in_progress' RETURNING id`. They now take `request_hash` and return `bool` (`False` = fenced off, stored response untouched).
- `IDEMPOTENCY_IN_PROGRESS_TIMEOUT_SECONDS` default 60 -> 600 (`.env.example` in sync); documented as "must exceed the slowest handler".
- `delete_expired_idempotency_keys` reads the row count through `CursorResult` instead of an untyped attribute.
- **BREAKING (helper API)**: `replay_or_start_idempotent_request` returns `JSONResponse | IdempotentCall | None`; `store_idempotent_response(call, ...)` takes that `IdempotentCall` (key, principal, request hash, resolved store) instead of reading `request.state`, and returns `bool`. The store is resolved and the enabled flag checked once.

## Capabilities

### New Capabilities
- `platform/idempotency`: reclaim exclusivity, fenced completion, in-progress timeout.

### Modified Capabilities
None.

## Impact

- Code: `app/modules/platform/idempotency/{service,http,adapters,store}.py`, `app/core/config/platform.py`, `.env.example`; tests under `tests/unit/modules/`.
- No schema change. No endpoint uses idempotency yet, so no caller migration.

## Follow-ups

- Fence limitation: a late original whose request is byte-identical to the reclaiming retry (same `request_hash`) can still complete the shared claim first. Closing it needs a per-claim token column (schema packet).
- No heartbeat: a handler that outlives the timeout can still be re-run. Raise the timeout rather than add a refresh loop.
