## ADDED Requirements

### Requirement: A failed handler releases the key

When the handler wrapped by `@idempotent` raises, the in-progress claim SHALL be released so the next request with the same key runs the handler again. The exception SHALL propagate unchanged.

#### Scenario: Retry after failure
- **WHEN** the first request raises and a second request arrives with the same key and body
- **THEN** the handler runs again and the second request is not answered with `idempotency_key_in_progress`

#### Scenario: Cancelled request
- **WHEN** the handler is cancelled
- **THEN** the claim is released

### Requirement: The replay equals the first response

The stored response SHALL be what the client received: the route's declared `status_code` (200 when none) and the body after the route's `response_model` filtering when one is declared. Any JSON-serializable body (object, list, scalar, null) SHALL be stored; a body that cannot be stored SHALL be rejected before the handler runs or stored without failing after it.

#### Scenario: Declared status
- **WHEN** a route declares `status_code=201` and is called twice with one key
- **THEN** both responses are 201 with the same body

#### Scenario: Response model hides a field
- **WHEN** the handler returns a field the `response_model` does not declare
- **THEN** neither the first response nor the replay contains it

#### Scenario: List body
- **WHEN** the handler returns a list
- **THEN** the replay returns the same list and the handler ran once

### Requirement: The request hash covers the query string

Two requests with the same key, method, path and body but different query strings SHALL be treated as different requests (the existing key-reuse conflict response).

#### Scenario: Different query
- **WHEN** the same key is reused with a different query string
- **THEN** the response is the existing mismatch conflict, and the handler does not run
