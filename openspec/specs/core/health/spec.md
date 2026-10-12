# core/health Specification

## Purpose
Readiness and liveness semantics during startup, normal running and graceful shutdown draining.

## Requirements

### Requirement: Readiness fails while draining

The application SHALL mark its `HealthService` draining at the start of shutdown,
before it waits for in-flight requests. While draining, `/readyz` SHALL return `503`
with status `draining` and SHALL NOT run dependency checks. `/healthz` SHALL keep
returning `200`.

#### Scenario: Shutdown with a request in flight
- **WHEN** shutdown begins while a request is still in flight
- **THEN** `/readyz` returns `503` with status `draining` and `/healthz` returns `200`

### Requirement: Graceful shutdown is on by default

`GRACEFUL_SHUTDOWN_ENABLED` SHALL default to `true`, and the container command SHALL
pass `--timeout-graceful-shutdown` with `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS` (default 30)
to uvicorn.

#### Scenario: Default settings
- **WHEN** settings are built without overrides
- **THEN** `GRACEFUL_SHUTDOWN_ENABLED` is `true`
