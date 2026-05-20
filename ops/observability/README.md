# Observability Profiles

Profiles in this folder are local development starting points. Application code should emit generic telemetry through adapter contracts and OpenTelemetry-compatible conventions; backend-specific routing belongs here.

The debug profile uses the OpenTelemetry Collector debug exporter so teams can validate emitted spans/logs locally without committing to Grafana, Datadog, Phoenix, or another backend.
