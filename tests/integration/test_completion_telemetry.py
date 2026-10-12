"""Completion edge emits GenAI metrics/spans through the Telemetry handle."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.bootstrap.application import create_app
from app.core.telemetry_otel import Telemetry
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from tests.factories import build_test_settings

HEADERS = {"Authorization": "Bearer test-token"}
SECRET = "do-not-export-this-prompt"  # pragma: allowlist secret
BODY = {"messages": [{"role": "user", "content": SECRET}]}


class _Rig:
    def __init__(self) -> None:
        self.spans = InMemorySpanExporter()
        self.reader = InMemoryMetricReader()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(self.spans))
        self.telemetry = Telemetry(
            tracer_provider=tracer_provider,
            meter_provider=MeterProvider(metric_readers=[self.reader]),
            request_model="configured-model",
        )

    def metrics(self) -> dict[str, list]:
        data = self.reader.get_metrics_data()
        found: dict[str, list] = {}
        if data is None:
            return found
        for resource in data.resource_metrics:
            for scope in resource.scope_metrics:
                for metric in scope.metrics:
                    found[metric.name] = list(metric.data.data_points)
        return found


class _FailingHandler:
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        raise RuntimeError("model down")

    async def stream(
        self, request: CompletionRequest
    ) -> AsyncIterator[CompletionStreamChunk]:
        raise RuntimeError("model down")
        yield CompletionStreamChunk(delta="")


async def _call(rig: _Rig, path: str, *, handler=None):
    kwargs = (
        {} if handler is None else {"completion_handler_factory": lambda r, s: handler}
    )
    app = create_app(settings=build_test_settings(), init_resources=False, **kwargs)
    async with app.router.lifespan_context(app):
        app.state.resources.telemetry = rig.telemetry
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(path, headers=HEADERS, json=BODY)
            _ = response.text
            return response


async def test_sync_completion_records_genai_histograms_without_content():
    rig = _Rig()

    response = await _call(rig, "/api/v1/completions")

    assert response.status_code == 200
    metrics = rig.metrics()
    [duration] = metrics["gen_ai.client.operation.duration"]
    assert duration.count == 1
    attrs = dict(duration.attributes)
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.request.model"] == "configured-model"
    assert attrs["gen_ai.response.model"] == "echo"
    assert attrs["app.completion.mode"] == "sync"
    assert attrs["app.completion.outcome"] == "ok"

    tokens = {
        dict(p.attributes)["gen_ai.token.type"]: p
        for p in metrics["gen_ai.client.token.usage"]
    }
    assert set(tokens) == {"input", "output"}
    assert tokens["input"].sum + tokens["output"].sum == 3
    assert "gen_ai.client.operation.time_to_first_chunk" not in metrics

    [span] = rig.spans.get_finished_spans()
    assert span.attributes is not None
    assert span.attributes["gen_ai.response.model"] == "echo"
    assert tuple(span.attributes["gen_ai.response.finish_reasons"]) == ("stop",)
    assert SECRET not in repr(dict(span.attributes)) + repr(metrics)


async def test_stream_completion_records_time_to_first_chunk():
    rig = _Rig()

    response = await _call(rig, "/api/v1/completions/stream")

    assert response.status_code == 200
    metrics = rig.metrics()
    [ttft] = metrics["gen_ai.client.operation.time_to_first_chunk"]
    assert ttft.count == 1
    [duration] = metrics["gen_ai.client.operation.duration"]
    assert dict(duration.attributes)["app.completion.mode"] == "stream"
    assert SECRET not in repr(metrics)


async def test_failed_completion_is_labelled_error_without_response_model():
    rig = _Rig()

    response = await _call(rig, "/api/v1/completions", handler=_FailingHandler())

    assert response.status_code == 500
    [duration] = rig.metrics()["gen_ai.client.operation.duration"]
    attrs = dict(duration.attributes)
    assert attrs["app.completion.outcome"] == "error"
    assert attrs["error.type"] == "error"
    assert "gen_ai.response.model" not in attrs
    [span] = rig.spans.get_finished_spans()
    assert not span.status.is_ok


async def test_without_telemetry_completions_still_work(client: AsyncClient):
    response = await client.post("/api/v1/completions", headers=HEADERS, json=BODY)

    assert response.status_code == 200


def test_create_app_instruments_fastapi_only_when_enabled():
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    off = create_app(settings=build_test_settings(), init_resources=False)
    on = create_app(
        settings=build_test_settings(
            OTEL_ENABLED=True, OTEL_EXPORTER_OTLP_ENDPOINT="http://127.0.0.1:1"
        ),
        init_resources=False,
    )
    try:
        assert getattr(off, "_is_instrumented_by_opentelemetry", False) is False
        assert on._is_instrumented_by_opentelemetry is True
    finally:
        FastAPIInstrumentor.uninstrument_app(on)


def test_unconfigured_request_model_is_omitted_not_empty():
    from time import time_ns

    from app.core.telemetry import CompletionObservation

    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    telemetry = Telemetry(
        tracer_provider=tracer_provider,
        meter_provider=MeterProvider(metric_readers=[InMemoryMetricReader()]),
        request_model="",
    )

    telemetry.record_completion(
        CompletionObservation(
            mode="sync",
            outcome="ok",
            started_ns=time_ns(),
            duration_s=0.01,
            ttft_s=None,
            model=None,
            finish_reason=None,
            input_tokens=None,
            output_tokens=None,
        )
    )

    (span,) = spans.get_finished_spans()
    assert "gen_ai.request.model" not in (span.attributes or {})
    assert span.name == "chat"
