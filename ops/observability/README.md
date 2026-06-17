# Observability Profiles

Profiles in this folder are local development starting points. Application code should emit generic telemetry through adapter contracts and OpenTelemetry-compatible conventions; backend-specific routing belongs here.

The debug profile uses the OpenTelemetry Collector debug exporter so teams can validate emitted spans/logs locally without committing to Grafana, Datadog, Phoenix, or another backend.

Use `OBSERVABILITY_BACKEND=otel_debug` with `OTEL_EXPORTER_OTLP_ENDPOINT` to make the app emit OpenTelemetry-style debug records through the observability adapter. The default `debug` backend stays in-process and vendor-neutral for tests and local development.
