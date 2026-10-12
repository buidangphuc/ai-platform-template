# core/telemetry Specification

## Purpose
Optional OpenTelemetry export of traces and GenAI metrics.

## Requirements

### Requirement: Telemetry is off by default and optional

`OTEL_ENABLED` SHALL default to `false`. While it is `false` the application SHALL NOT
build any OpenTelemetry provider or instrument FastAPI, and SHALL import and run
without the `otel` extra. Enabling it without `OTEL_EXPORTER_OTLP_ENDPOINT` SHALL be a
settings error; enabling it without the extra installed SHALL fail at startup with a
message naming the extra.

#### Scenario: Default settings
- **WHEN** the application starts with default settings
- **THEN** `ApplicationResources.telemetry` is `None` and no provider exists

#### Scenario: Enabled without an endpoint
- **WHEN** settings are built with `OTEL_ENABLED=true` and no endpoint
- **THEN** validation fails naming `OTEL_EXPORTER_OTLP_ENDPOINT`

### Requirement: Telemetry lifecycle is owned by bootstrap

When enabled, `TelemetryAddon` SHALL build a tracer and meter provider with OTLP/HTTP
exporters, expose a typed handle as `ApplicationResources.telemetry`, and flush and
shut the providers down when the runtime closes. `create_app` SHALL apply FastAPI
instrumentation in a single call gated by `OTEL_ENABLED`.

#### Scenario: Runtime closes
- **WHEN** the runtime exits with telemetry enabled
- **THEN** the providers are shut down

### Requirement: Completions emit GenAI telemetry without content

When telemetry is open, each sync or stream completion SHALL record the histograms
`gen_ai.client.operation.duration`, `gen_ai.client.token.usage` (attribute
`gen_ai.token.type` of `input` or `output`) and, for streams,
`gen_ai.client.operation.time_to_first_chunk`, plus one span carrying
`gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.response.finish_reasons` and the
outcome. Failed completions SHALL carry `error.type`. No prompt or output content SHALL
be recorded. The existing completion log line SHALL be unchanged, and completions SHALL
behave identically when telemetry is off.

#### Scenario: Sync completion
- **WHEN** a sync completion succeeds with telemetry open
- **THEN** the duration and token-usage histograms carry the model and outcome attributes and no message content appears in any attribute

#### Scenario: Streamed completion
- **WHEN** a stream completes with telemetry open
- **THEN** the time-to-first-chunk histogram has one data point
