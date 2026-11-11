## ADDED Requirements

### Requirement: Optional one-line guards

`require_quota(resource, cost=1)` SHALL be a dependency that reserves quota for `principal.id` before the handler runs and answers `429` with `Retry-After` when exceeded. `@idempotent` SHALL be a decorator that replays a stored response for a repeated `Idempotency-Key`, stores the response of a first call, and does nothing without the header. No route SHALL use either by default, and their docstrings SHALL say they are opt-in examples.

#### Scenario: Quota exceeded
- **WHEN** a route with `require_quota("x")` is called past its limit
- **THEN** the response is `429` and the handler did not run

#### Scenario: Idempotent replay
- **WHEN** a decorated route is called twice with the same key and body
- **THEN** the handler runs once and the second response equals the first

#### Scenario: No default usage
- **WHEN** searching `app/api/` for `require_quota` and `idempotent`
- **THEN** there are no matches
