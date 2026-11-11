## MODIFIED Requirements

### Requirement: One observation per completion

`LLMInstance` SHALL take an `LlmSink` and record exactly one `LlmObservation` per `ainvoke()` (mode `sync`) or `astream()` (mode `stream`) call, with outcome `ok`, `error`, `timeout` or `disconnected`, duration, model, finish reason and token usage; TTFT only for streams. It SHALL never record prompt or output content. `CompletionService` SHALL NOT record observations.

#### Scenario: Worker completions are observed
- **WHEN** the worker runs a completion task with `LLM_ENABLED=true`
- **THEN** the sink receives one observation with mode `sync` and outcome `ok`

#### Scenario: Client disconnects mid-stream
- **WHEN** the client disconnects while the stream waits for the next chunk
- **THEN** the sink receives exactly one observation with outcome `disconnected` and the handler's cleanup runs

#### Scenario: Failure is labelled
- **WHEN** the model call raises
- **THEN** the observation has outcome `error` and the exception propagates

### Requirement: Sinks composed once in bootstrap

`LlmAddon` SHALL build the instance's sink as `FanOutSink` of `LogLlmSink` plus the OTel telemetry handle when `OTEL_ENABLED`. The log line format SHALL stay `completion mode=… outcome=… model=… duration_ms=… ttft_ms=… finish_reason=… input_tokens=… output_tokens=… total_tokens=…`.

#### Scenario: Telemetry off
- **WHEN** `OTEL_ENABLED` is false and `LLM_ENABLED` is true
- **THEN** completions still return `200` and still log one completion line

#### Scenario: Echo handler
- **WHEN** `LLM_ENABLED` is false
- **THEN** completions return `200` and no completion line is logged
