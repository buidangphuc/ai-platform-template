## ADDED Requirements

### Requirement: The route guard carries its policy

`require_quota(policy: QuotaPolicy, cost: int = 1)` SHALL reserve `cost` for the authenticated principal against `policy`. `QuotaService` SHALL take the policy on every call; `QuotaPolicyStore`, `StaticQuotaPolicyStore` and the `policies` argument of `build_quota_service` SHALL NOT exist. The guard SHALL work with the service built by the quota addon.

#### Scenario: Guard works with the shipped addon
- **WHEN** an app opens the quota addon and a route depends on `require_quota(policy)`
- **THEN** requests under the limit pass and the request over the limit gets 429 with `Retry-After`

#### Scenario: Quota disabled
- **WHEN** `QUOTA_ENABLED` is false and the route is called
- **THEN** the response is the existing service-unavailable error, not a 500

### Requirement: A refunded reservation is charged again

A reserve with an idempotency key whose reservation was refunded SHALL charge again and return the reservation as reserved, or be rejected when the limit is exhausted, on both adapters. A key whose reservation is reserved or finalized SHALL return it without charging, as before.

#### Scenario: Retry after refund
- **WHEN** reserve(key), refund, reserve(key) run in order
- **THEN** usage equals one cost and the reservation is reserved

#### Scenario: Retry after refund at the limit
- **WHEN** the limit was filled by other reservations before the retry
- **THEN** the retry is rejected

### Requirement: Mongo reserve charges before it records

The Mongo adapter SHALL increment the counter conditionally (only while `used + cost <= limit`) before inserting the reservation, SHALL undo the increment and return the existing reservation when the insert hits the idempotency key, and SHALL never let `used` go below zero on refund. It SHALL NOT migrate counters between windows.

#### Scenario: Rejected request is never visible as reserved
- **WHEN** a reserve is rejected for the limit
- **THEN** no reservation document exists for its key at any point

#### Scenario: Concurrent same-key retries
- **WHEN** several reserves with one key run concurrently under the limit
- **THEN** all return the same reservation and usage equals one cost

#### Scenario: Refund floor
- **WHEN** a reservation is refunded and the counter is already zero
- **THEN** `used` stays zero
