# business/completions-observation Specification

## Purpose
Completion observation and stream deadlines owned by `CompletionService`, so every caller (API, worker) is measured the same way.

## Requirements

### Requirement: One observation per completion

`CompletionService` SHALL take a `CompletionSink` and record exactly one `CompletionObservation` per `complete()` (mode `sync`) or `stream()` (mode `stream`) call, with outcome `ok`, `error`, `timeout` or `disconnected`, duration, model, finish reason and token usage; TTFT only for streams. It SHALL never record prompt or output content.

#### Scenario: Worker completions are observed
- **WHEN** the worker runs a completion task
- **THEN** the sink receives one observation with mode `sync` and outcome `ok`

#### Scenario: Client disconnects mid-stream
- **WHEN** the client disconnects while the stream waits for the next chunk
- **THEN** the sink receives exactly one observation with outcome `disconnected` and the handler's cleanup runs

#### Scenario: Failure is labelled
- **WHEN** the handler raises
- **THEN** the observation has outcome `error` and the exception propagates

### Requirement: Stream deadlines are a service policy

`CompletionService` SHALL take a `StreamPolicy(first_token_timeout, idle_timeout)` built by bootstrap from `STREAM_FIRST_TOKEN_TIMEOUT_SECONDS` and `STREAM_IDLE_TIMEOUT_SECONDS`, and raise `StreamTimeoutError` (`504`, code `stream_timeout`) from `stream()` when the handler misses a deadline, recording outcome `timeout`.

#### Scenario: First token too slow
- **WHEN** the handler yields nothing within `first_token_timeout`
- **THEN** `stream()` raises `StreamTimeoutError` and the observation outcome is `timeout`

### Requirement: Sinks composed once in bootstrap

Bootstrap SHALL build the service's sink as `FanOutSink` of `LogCompletionSink` plus the OTel telemetry handle when `OTEL_ENABLED`. The log line format SHALL stay `completion mode=… outcome=… model=… duration_ms=… ttft_ms=… finish_reason=… input_tokens=… output_tokens=… total_tokens=…`.

#### Scenario: Telemetry off
- **WHEN** `OTEL_ENABLED` is false
- **THEN** completions still return `200` and still log one completion line
