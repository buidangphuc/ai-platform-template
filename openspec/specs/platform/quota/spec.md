# platform/quota Specification

## Purpose
Token and request quota reservations that stay exactly-once and correct under concurrent retries, on Postgres and Mongo.

## Requirements

### Requirement: Refund and finalize are exactly-once under concurrency
The quota store SHALL apply a reservation's transition from reserved to refunded, or from reserved to finalized, at most once, regardless of how many callers attempt it concurrently. Capacity SHALL be returned to the counter only by the caller whose refund performed the transition, and a counter SHALL never become negative because of repeated refunds.

#### Scenario: Concurrent refunds of one reservation
- **WHEN** two callers refund the same reserved reservation at the same time
- **THEN** both calls succeed and the counter is decremented by the reservation cost exactly once

#### Scenario: Refund racing finalize
- **WHEN** a refund and a finalize of the same reserved reservation run at the same time
- **THEN** exactly one of them takes effect and the other is rejected because the reservation is already in the opposite terminal state

#### Scenario: Unknown reservation
- **WHEN** a refund or finalize targets a reservation that does not exist
- **THEN** the store reports the reservation as not found

### Requirement: Same idempotency key returns the existing reservation
Reserving with an idempotency key that already has a reservation for the same subject, resource and window SHALL return that existing reservation and SHALL NOT charge the counter again, including when the duplicate requests arrive concurrently. Concurrent duplicates SHALL NOT fail with an internal error.

#### Scenario: Concurrent duplicate reserve
- **WHEN** two reserve calls with the same idempotency key run at the same time
- **THEN** both return the same reservation and the counter is charged once

#### Scenario: Over-limit reserve leaves no residue
- **WHEN** a reserve is rejected because the limit would be exceeded
- **THEN** no reservation is recorded and the counter is unchanged

### Requirement: Timestamps are timezone-aware
Datetimes returned by the quota stores, including the Mongo-backed store, SHALL be timezone-aware (UTC) so they can be compared with the current time across window rollovers.

#### Scenario: Window rollover on Mongo
- **WHEN** a reserve or usage query runs after the previous window has rolled over
- **THEN** it completes without a timezone comparison error
