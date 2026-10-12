# Observability Profiles

Profiles in this folder are local development starting points. Application code should emit generic telemetry through adapter contracts and OpenTelemetry-compatible conventions; backend-specific routing belongs here.

The debug profile (`otel-collector.debug.yaml`) uses the OpenTelemetry Collector debug exporter so teams can validate emitted spans/logs locally without committing to Grafana, Datadog, Phoenix, or another backend.

The app has no `OBSERVABILITY_BACKEND` or `OTEL_EXPORTER_OTLP_ENDPOINT` setting: `Settings` forbids unknown env vars, and `tests/unit/core/test_config.py` pins both as absent. The only tracing integration today is Langfuse (`LANGFUSE_*` in `.env.example`). To route telemetry through this collector profile, add a real setting and adapter first, and update this document with it.
