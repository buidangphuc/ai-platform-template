"""OpenTelemetry-backed telemetry (optional ``otel`` extra).

Imported lazily, only after ``require_otel()`` passed. Emits the GenAI client
metrics and one span per completion; never prompt or output content.
"""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode, set_tracer_provider

from app.core.config import Settings
from app.core.telemetry import CompletionObservation

_DURATION_BUCKETS = (0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12)
_TOKEN_BUCKETS = (1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144)
_HEALTH_PATHS = "healthz,readyz"


class Telemetry:
    """Typed handle over the providers; also the completions ``CompletionSink``."""

    def __init__(
        self,
        *,
        tracer_provider: TracerProvider,
        meter_provider: MeterProvider,
        request_model: str,
    ) -> None:
        self.tracer_provider = tracer_provider
        self.meter_provider = meter_provider
        self._request_model = request_model
        self._tracer = tracer_provider.get_tracer("app.completions")
        meter = meter_provider.get_meter("app.completions")
        self._duration = meter.create_histogram(
            "gen_ai.client.operation.duration",
            unit="s",
            description="GenAI operation duration",
            explicit_bucket_boundaries_advisory=_DURATION_BUCKETS,
        )
        self._tokens = meter.create_histogram(
            "gen_ai.client.token.usage",
            unit="{token}",
            description="Input and output tokens per operation",
            explicit_bucket_boundaries_advisory=_TOKEN_BUCKETS,
        )
        self._ttft = meter.create_histogram(
            "gen_ai.client.operation.time_to_first_chunk",
            unit="s",
            description="Time to the first streamed chunk",
            explicit_bucket_boundaries_advisory=_DURATION_BUCKETS,
        )

    def record_completion(self, observation: CompletionObservation) -> None:
        attributes: dict[str, str] = {
            "gen_ai.operation.name": "chat",
            "app.completion.mode": observation.mode,
            "app.completion.outcome": observation.outcome,
        }
        if self._request_model:
            attributes["gen_ai.request.model"] = self._request_model
        if observation.model:
            attributes["gen_ai.response.model"] = observation.model
        failed = observation.outcome != "ok"
        if failed:
            attributes["error.type"] = observation.outcome

        self._duration.record(observation.duration_s, attributes)
        if observation.ttft_s is not None:
            self._ttft.record(observation.ttft_s, attributes)
        for token_type, count in (
            ("input", observation.input_tokens),
            ("output", observation.output_tokens),
        ):
            if count is not None:
                self._tokens.record(
                    count, {**attributes, "gen_ai.token.type": token_type}
                )

        span = self._tracer.start_span(
            " ".join(
                part
                for part in ("chat", observation.model or self._request_model)
                if part
            ),
            kind=SpanKind.CLIENT,
            start_time=observation.started_ns,
            attributes=attributes,
        )
        if observation.finish_reason:
            span.set_attribute(
                "gen_ai.response.finish_reasons", [observation.finish_reason]
            )
        if observation.input_tokens is not None:
            span.set_attribute("gen_ai.usage.input_tokens", observation.input_tokens)
        if observation.output_tokens is not None:
            span.set_attribute("gen_ai.usage.output_tokens", observation.output_tokens)
        if failed:
            span.set_status(Status(StatusCode.ERROR))
        span.end()

    def shutdown(self) -> None:
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()


def build_telemetry(settings: Settings) -> Telemetry:
    resource = Resource.create({SERVICE_NAME: settings.OTEL_SERVICE_NAME})
    base = settings.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/")
    tracer_provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.OTEL_TRACES_SAMPLE_RATIO)),
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base}/v1/traces"))
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{base}/v1/metrics")
            )
        ],
    )
    return Telemetry(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        request_model=settings.CHAT_MODEL,
    )


def install_globals(telemetry: Telemetry) -> None:
    """Point the FastAPI instrumentation (global API) at these providers."""
    set_tracer_provider(telemetry.tracer_provider)
    set_meter_provider(telemetry.meter_provider)


def instrument_fastapi(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(app, excluded_urls=_HEALTH_PATHS)
