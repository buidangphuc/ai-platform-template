## ADDED Requirements

### Requirement: An expired or stuck key is reclaimed by exactly one retry
When a key's record has expired or is still `in_progress` past the in-progress timeout, concurrent retries SHALL serialize on the record so that exactly one of them reclaims the key and proceeds to run its handler; the others SHALL observe the refreshed record and be rejected as in progress (or served from cache, or as a key conflict).

#### Scenario: Concurrent retries of a stuck key
- **WHEN** two retries arrive at the same time for a key stuck in progress beyond the timeout
- **THEN** one reclaims the key and the other fails with `idempotency_key_in_progress`

#### Scenario: Concurrent retries of an expired key
- **WHEN** two retries arrive at the same time for an expired key
- **THEN** exactly one reclaims it

### Requirement: Completing a response is fenced
Storing a response SHALL succeed only while the record is still `in_progress` for the same request hash. A write that fails the fence SHALL leave the stored record untouched and report that it did not store.

#### Scenario: Late original after a reclaim
- **WHEN** the original request finishes after a retry with a different request hash reclaimed the key
- **THEN** the original's response is not stored and the retry's response is the one cached

#### Scenario: Already completed
- **WHEN** a response is stored for a record that is already completed
- **THEN** the first stored response is kept

### Requirement: In-progress timeout exceeds realistic handler time
`IDEMPOTENCY_IN_PROGRESS_TIMEOUT_SECONDS` SHALL default to a value above a realistic LLM call deadline (600 seconds), and its documentation SHALL state that it is measured from the claim and must exceed the slowest handler.

#### Scenario: Default
- **WHEN** settings are loaded without an override
- **THEN** the in-progress timeout is 600 seconds

### Requirement: Typed HTTP handoff
`replay_or_start_idempotent_request` SHALL return the claimed call as a typed handle that `store_idempotent_response` consumes, and SHALL resolve the store and the enabled flag once, without relying on `request.state`.

#### Scenario: Claim then store
- **WHEN** a request with an `Idempotency-Key` claims the key and the handler succeeds
- **THEN** the returned `IdempotentCall` is passed to `store_idempotent_response`, which stores through the store resolved at claim time
