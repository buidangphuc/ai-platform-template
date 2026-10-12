## Why

The only observability for completions is one log line, and the only tracing is
Langfuse. Teams on an OTLP backend (Grafana, Datadog, Tempo) get no latency,
token or time-to-first-token metrics. `ops/observability/README.md` documented
profiles for settings that do not exist.

## What Changes

- New optional extra `otel` (api, sdk, OTLP/HTTP exporter, FastAPI instrumentation).
  The app imports and runs without it.
- Settings `OTEL_ENABLED` (default `false`), `OTEL_SERVICE_NAME`,
  `OTEL_EXPORTER_OTLP_ENDPOINT` (required when enabled), `OTEL_TRACES_SAMPLE_RATIO`.
- `TelemetryAddon` builds a tracer and meter provider with OTLP exporters, stores a
  typed `Telemetry` handle on `ApplicationResources.telemetry`, and shuts the
  providers down (flush) through the exit stack. Off means no provider is built.
- `create_app` applies FastAPI auto-instrumentation in one call, gated by the setting
  (health probes excluded).
- The completions edge reports each finished completion to a `CompletionSink`:
  the `Telemetry` handle when open, else a no-op sink resolved once. GenAI metrics
  `gen_ai.client.operation.duration`, `gen_ai.client.token.usage`,
  `gen_ai.client.operation.time_to_first_chunk` (streams) and one `chat` span with
  `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.response.finish_reasons`
  and the outcome. No prompt or output content. The log line is unchanged.
- `ops/observability/README.md` describes the real settings and the extra.

## Capabilities

### New Capabilities

- `core/telemetry`: optional OpenTelemetry export of traces and GenAI metrics.

### Modified Capabilities

None.

## Impact

- Code: `app/core/{telemetry,telemetry_otel}.py`, `app/core/config/{telemetry,__init__}.py`,
  `app/bootstrap/{application,resources}.py`, `app/bootstrap/addons/{telemetry,base}.py`,
  `app/api/v1/completions/{observability,sync,stream}.py`, `pyproject.toml`, `uv.lock`,
  `.env.example`, `ops/observability/README.md`.
- `OBSERVABILITY_BACKEND` stays absent; `OTEL_EXPORTER_OTLP_ENDPOINT` is now a setting.
- The tracer and meter providers are also registered globally, because the FastAPI
  instrumentation is applied in `create_app` before the providers exist and resolves
  them lazily. The global setter works once per process.
- Unverified: export to a live collector (tests use in-memory exporters).
- Out of scope: worker/queue spans, trace-context propagation into tasks, Langfuse
  bridging, prompt/output capture.
