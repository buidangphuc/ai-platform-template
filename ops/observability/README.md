# Observability

Optional OpenTelemetry export of traces and GenAI metrics over OTLP/HTTP. Off by default; when off, nothing is imported or built and completions emit only their structured log line.

## Enable

1. Install the extra: `uv sync --extra otel` (or `pip install '.[otel]'`). Without it the app runs normally; `OTEL_ENABLED=true` then fails at startup naming the extra.
2. Set the settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `OTEL_ENABLED` | `false` | Turn on tracing and metrics. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty | Base OTLP/HTTP URL, e.g. `http://localhost:4318` (the app appends `/v1/traces` and `/v1/metrics`). Required when enabled. |
| `OTEL_SERVICE_NAME` | `ai-platform` | `service.name` resource attribute. |
| `OTEL_TRACES_SAMPLE_RATIO` | `1.0` | Head sampling ratio in `[0, 1]`, parent-based. |

## What is emitted

- FastAPI auto-instrumentation (HTTP server spans and metrics; `healthz` and `readyz` excluded).
- Per completion (sync and stream), at the completions edge: a `chat` span and the GenAI client histograms `gen_ai.client.operation.duration` (s), `gen_ai.client.token.usage` (`gen_ai.token.type` = `input` or `output`) and, for streams, `gen_ai.client.operation.time_to_first_chunk` (s). Attributes: `gen_ai.operation.name`, `gen_ai.request.model` (`CHAT_MODEL`), `gen_ai.response.model`, `app.completion.mode`, `app.completion.outcome`, `error.type` on failure; the span also carries `gen_ai.response.finish_reasons` and token counts.
- Never prompt or output content.

Langfuse (`LANGFUSE_*`) is a separate, independent tracing integration for LLM calls.

## Local collector

`otel-collector.debug.yaml` runs the OpenTelemetry Collector with the debug exporter so you can see what the app emits without choosing a backend:

```bash
docker run --rm -p 4318:4318 \
  -v "$PWD/ops/observability/otel-collector.debug.yaml:/etc/otelcol/config.yaml" \
  otel/opentelemetry-collector:latest --config /etc/otelcol/config.yaml
OTEL_ENABLED=true OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 uv run uvicorn main:app
```

Route to a real backend by changing the collector's exporters, not the app.

## Not covered

Worker and queue spans, trace-context propagation into async tasks, and prompt/output capture.
