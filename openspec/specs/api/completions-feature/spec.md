# api/completions-feature Specification

## Purpose
The canonical API feature shape, using `/api/v1/completions` as the reference.

## Requirements

### Requirement: Views are thin

A completions view SHALL read the service from `get_app_resources(request.app)`, call one service method, and return the response built with `model_validate`. Views SHALL NOT time, log, record telemetry, apply deadlines or mint ids.

#### Scenario: Sync completion
- **WHEN** a client posts a valid request to `POST /api/v1/completions`
- **THEN** the response is `200` with `id` starting `cmpl_`, `object="completion"`, and the result's `content`, `model`, `usage`, `finish_reason`, `metadata`

#### Scenario: Feature package is small
- **WHEN** listing `app/api/v1/completions/`
- **THEN** it holds only `__init__.py`, `router.py` and `tasks.py`

### Requirement: Streaming goes through the shared SSE helper

Feature streams SHALL be returned by `app/api/sse.py` `event_stream_response`, which primes the first event before sending headers, sends `: ping` comments every `SSE_HEARTBEAT_SECONDS` while waiting, turns an `AppError` after the first event into `event: error` with its code (other exceptions → `stream_error`, logged, no exception text), and closes the source under a shielded cancel scope on disconnect.

#### Scenario: Errors before the first event stay JSON
- **WHEN** an input guard rejects a stream request, the handler fails before its first chunk, or the first token deadline passes
- **THEN** the response is the JSON error envelope (`422 guardrail_input_violation`, `500 internal_server_error`, `504 stream_timeout`), not a `200` stream

#### Scenario: Stream contract unchanged
- **WHEN** a stream completes
- **THEN** headers include `Cache-Control: no-cache` and `X-Accel-Buffering: no`, deltas arrive as `data: {"type": "content.delta", ...}`, and the last frame is `data: {"type": "done"}` plus any `usage`, `finish_reason`, `model`

#### Scenario: Mid-stream failure
- **WHEN** the idle deadline passes or the handler raises after the first chunk
- **THEN** the last frame is `event: error` with code `stream_timeout` or `stream_error` and no `done` frame

### Requirement: Routes declared once

`router.py` SHALL declare the `/completions` prefix, tag and auth dependency once. The task routes SHALL stay mounted only when `TASKS_ENABLED`, and take the principal as a parameter without a duplicate router-level dependency.

#### Scenario: Auth still required
- **WHEN** `POST /api/v1/completions` is called without credentials
- **THEN** the response is `401`
