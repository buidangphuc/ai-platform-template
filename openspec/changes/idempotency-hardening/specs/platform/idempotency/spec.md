## ADDED Requirements

### Requirement: Completion is fenced on a per-claim token
Every claim or reclaim of a key SHALL record a fresh claim token and hand it to the claimer. Storing a response SHALL succeed only while the record is `in_progress` with that token, regardless of the request hash. A write that fails the fence SHALL leave the record untouched and report that it did not store.

#### Scenario: Late original with an identical request
- **WHEN** a retry with the same request hash reclaims a stuck key and the original request then finishes
- **THEN** the original's response is not stored and the retry's response is the one cached

#### Scenario: Pre-migration rows
- **WHEN** a record has no claim token
- **THEN** no write can complete it; it expires or is reclaimed like any stuck record

### Requirement: Expired keys are purged by the worker
While the worker runs and an idempotency store exists, it SHALL periodically delete records past `expires_at`, in bounded batches (`delete_expired` requires a positive `limit`) repeated until a batch is short. The loop SHALL continue after a failed iteration.

#### Scenario: Backlog of expired keys
- **WHEN** more expired keys exist than the batch size alongside unexpired ones
- **THEN** only expired keys are deleted, at most the batch size per statement
