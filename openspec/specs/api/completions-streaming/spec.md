# api/completions-streaming Specification

## Purpose
The server-sent-events contract of `POST /api/v1/completions/stream` and the
per-completion log line.

## Requirements

### Requirement: Stream handlers yield typed chunks

`CompletionHandler.stream` SHALL return `AsyncIterator[CompletionStreamChunk]`. A
chunk SHALL carry `delta` and MAY carry `model`, `usage` and `finish_reason`.

#### Scenario: Echo handler reports usage
- **WHEN** the echo handler streams a completion
- **THEN** its single chunk carries the delta, `model`, `usage` and `finish_reason`

### Requirement: Pre-flight failures are normal errors

The stream endpoint SHALL await the first chunk before it sends any response
headers, so a failure raised before the first chunk returns the standard JSON error
envelope with the error's own status.

#### Scenario: Input guard blocks a stream
- **WHEN** an input guard raises `GuardrailViolation` for a stream request
- **THEN** the response is `422` JSON with code `guardrail_input_violation`, not a `200` event stream

#### Scenario: Handler fails on startup
- **WHEN** the handler raises before yielding its first chunk
- **THEN** the response is the `internal_server_error` JSON envelope and carries no exception text

### Requirement: Stream responses are proxy-safe SSE

The stream response SHALL set `Cache-Control: no-cache` and `X-Accel-Buffering: no`,
and SHALL write a `: ping` comment frame every `SSE_HEARTBEAT_SECONDS` while it waits
for the next chunk.

#### Scenario: Slow model
- **WHEN** the handler takes longer than the heartbeat interval to produce a chunk
- **THEN** the client receives `: ping` comment frames until the chunk arrives

### Requirement: Streams have deadlines

A stream SHALL fail with code `stream_timeout` when no chunk arrives within
`STREAM_FIRST_TOKEN_TIMEOUT_SECONDS` (first chunk) or `STREAM_IDLE_TIMEOUT_SECONDS`
(between chunks).

#### Scenario: Timeout before the first chunk
- **WHEN** the first chunk does not arrive within the first-token deadline
- **THEN** the response is `504` JSON with code `stream_timeout`

#### Scenario: Timeout after the first chunk
- **WHEN** a later chunk does not arrive within the idle deadline
- **THEN** the stream emits `event: error` with `{"type":"error","code":"stream_timeout"}` and closes without a `done` event

### Requirement: Mid-stream failures never leak

When the stream fails after the response has started, it SHALL emit
`event: error` with `{"type":"error","code":<safe code>}` and close. The code SHALL be
the error's stable code for an application error and `stream_error` otherwise. The
frame SHALL NOT contain exception text or a stack trace.

#### Scenario: Handler raises mid-stream
- **WHEN** the handler raises an unexpected exception after yielding a chunk
- **THEN** the last frame is `event: error` with code `stream_error`, and the body contains neither the exception message nor a traceback

### Requirement: Done event reports usage

The `done` event SHALL include `usage`, `finish_reason` and `model` when the handler
reported them, and SHALL otherwise be `{"type":"done"}`.

#### Scenario: Final chunk carries usage
- **WHEN** the last chunk carries `usage` and `finish_reason`
- **THEN** the `done` event contains them

### Requirement: One log line per completion

Each sync or stream completion SHALL emit one log line with `mode`, `outcome`,
`model`, `duration_ms`, `ttft_ms` (stream only), `finish_reason` and token counts,
and SHALL NOT include prompt or output content.

#### Scenario: Stream completes
- **WHEN** a stream finishes normally
- **THEN** one `completion` line with `outcome=ok` is logged and it contains no message text
