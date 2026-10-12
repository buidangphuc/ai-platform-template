# core/health-drain Specification

## Purpose
Make the draining readiness state observable before the listener closes.

## Requirements

### Requirement: Readiness is observable during the shutdown delay

On the first SIGTERM or SIGINT the server entry SHALL mark the application's
`HealthService` draining, keep accepting connections for
`SHUTDOWN_READINESS_DELAY_SECONDS`, and only then begin uvicorn's graceful shutdown.
A value of `0` SHALL begin shutdown immediately. `SHUTDOWN_READINESS_DELAY_SECONDS`
SHALL default to `5` and reject negative values.

#### Scenario: Probe during the delay
- **WHEN** SIGTERM arrives and a probe requests `/readyz` within the delay
- **THEN** the connection is accepted and the response is `503` with status `draining`

#### Scenario: Delay elapsed
- **WHEN** the delay has elapsed
- **THEN** the listener closes, in-flight requests drain, and the process exits `0`

### Requirement: A second signal forces exit

A second SIGTERM or SIGINT SHALL cancel the remaining delay and force shutdown.

#### Scenario: Operator repeats the signal
- **WHEN** a second signal arrives during the delay
- **THEN** shutdown proceeds immediately with forced exit

### Requirement: Container runs the draining entry

The Dockerfile `CMD` SHALL be the exec-form `python -m app.serve`, so PID 1 receives
signals, with host and port from `SERVER_HOST` / `SERVER_PORT` (default `0.0.0.0:8000`)
and the graceful timeout from `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS`.

#### Scenario: docker stop
- **WHEN** `docker stop` sends SIGTERM to the container
- **THEN** `/readyz` returns `503` for about the delay before connections are refused
