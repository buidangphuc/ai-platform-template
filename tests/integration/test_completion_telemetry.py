"""LLM calls emit GenAI metrics/spans through the Telemetry handle."""

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from loguru import logger

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.bootstrap.application import create_app
from app.core.telemetry import FanOutSink, LogLlmSink
from app.core.telemetry_otel import Telemetry
from app.modules.ai.llm.runtime import build_llm_instance
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


USAGE = {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}
META = {"model_name": "fake-served", "finish_reason": "stop"}


class _UsageModel(FakeListChatModel):
    fail: bool = False

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.fail:
            raise RuntimeError("model down")
        message = AIMessage(
            content="fake", usage_metadata=USAGE, response_metadata=META
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        if self.fail:
            raise RuntimeError("model down")
        yield ChatGenerationChunk(message=AIMessageChunk(content="fa"))
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="ke", usage_metadata=USAGE, response_metadata=META
            )
        )


class _RigAddon:
    name = "test-telemetry"

    def __init__(self, rig: _Rig, *, fail: bool = False) -> None:
        self.rig = rig
        self.fail = fail

    def is_enabled(self, settings) -> bool:
        return True

    async def open(self, resources, settings, stack) -> None:
        resources.telemetry = self.rig.telemetry
        resources.llm = build_llm_instance(
            settings,
            instance_id="t",
            service_name="test",
            model_builder=lambda target: _UsageModel(responses=["x"], fail=self.fail),
            sink=FanOutSink([LogLlmSink(), self.rig.telemetry]),
        )


async def _call(
    rig: _Rig, path: str, *, logs: list[str] | None = None, fail: bool = False
):
    app = create_app(
        settings=build_test_settings(LLM_ENABLED=True, CHAT_MODEL="configured-model"),
        init_resources=False,
        resource_addons=(_RigAddon(rig, fail=fail),),
    )
    sink = None if logs is None else logger.add(logs.append, format="{message}")
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                response = await client.post(path, headers=HEADERS, json=BODY)
                _ = response.text
                return response
    finally:
        if sink is not None:
            logger.remove(sink)


async def test_sync_completion_records_genai_histograms_without_content():
    rig = _Rig()

    logs: list[str] = []

    response = await _call(rig, "/api/v1/completions", logs=logs)

    assert response.status_code == 200
    [line] = [ln for ln in logs if ln.startswith("completion ")]
    assert "mode=sync outcome=ok model=fake-served" in line
    assert "input_tokens=1 output_tokens=2 total_tokens=3" in line
    metrics = rig.metrics()
    [duration] = metrics["gen_ai.client.operation.duration"]
    assert duration.count == 1
    attrs = dict(duration.attributes)
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.request.model"] == "configured-model"
    assert attrs["gen_ai.response.model"] == "fake-served"
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
    assert span.attributes["gen_ai.response.model"] == "fake-served"
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

    response = await _call(rig, "/api/v1/completions", fail=True)

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

    from app.core.telemetry import LlmObservation

    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    telemetry = Telemetry(
        tracer_provider=tracer_provider,
        meter_provider=MeterProvider(metric_readers=[InMemoryMetricReader()]),
        request_model="",
    )

    telemetry.record_llm(
        LlmObservation(
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
