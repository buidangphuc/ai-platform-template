"""CompletionService records one observation per call and owns stream deadlines."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from loguru import logger

from app.core.telemetry import (
    CompletionObservation,
    FanOutSink,
    LogCompletionSink,
)
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
    CompletionUsage,
)
from app.modules.business.completions.service import (
    CompletionService,
    StreamPolicy,
    StreamTimeoutError,
)

USAGE = CompletionUsage(input_tokens=2, output_tokens=3, total_tokens=5)


class _Sink:
    def __init__(self) -> None:
        self.observations: list[CompletionObservation] = []

    def record_completion(self, observation: CompletionObservation) -> None:
        self.observations.append(observation)


class _Handler:
    def __init__(self, *steps: CompletionStreamChunk | float | Exception) -> None:
        self.steps = steps
        self.closed = False
        self.error: Exception | None = None

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if self.error:
            raise self.error
        return CompletionResult(
            content="ok", model="m", usage=USAGE, finish_reason="stop"
        )

    async def stream(
        self, request: CompletionRequest
    ) -> AsyncGenerator[CompletionStreamChunk, None]:
        try:
            for step in self.steps:
                if isinstance(step, CompletionStreamChunk):
                    yield step
                elif isinstance(step, Exception):
                    raise step
                else:
                    await asyncio.sleep(step)
        finally:
            self.closed = True


def _request() -> CompletionRequest:
    return CompletionRequest(messages=[{"role": "user", "content": "hi"}])


def _service(
    handler: _Handler, first: float = 1, idle: float = 1
) -> tuple[CompletionService, _Sink]:
    sink = _Sink()
    service = CompletionService(
        handler,
        sink=sink,
        policy=StreamPolicy(first_token_timeout=first, idle_timeout=idle),
    )
    return service, sink


async def test_complete_records_one_sync_observation() -> None:
    service, sink = _service(_Handler())

    await service.complete(_request())

    (obs,) = sink.observations
    assert (obs.mode, obs.outcome, obs.model, obs.finish_reason) == (
        "sync",
        "ok",
        "m",
        "stop",
    )
    assert (obs.input_tokens, obs.output_tokens, obs.total_tokens) == (2, 3, 5)
    assert obs.ttft_s is None


async def test_complete_failure_is_labelled_error_and_propagates() -> None:
    handler = _Handler()
    handler.error = RuntimeError("boom")
    service, sink = _service(handler)

    with pytest.raises(RuntimeError):
        await service.complete(_request())

    assert [o.outcome for o in sink.observations] == ["error"]


async def test_stream_records_ttft_usage_and_model() -> None:
    handler = _Handler(
        CompletionStreamChunk(delta="a", model="m"),
        CompletionStreamChunk(delta="", usage=USAGE, finish_reason="stop"),
    )
    service, sink = _service(handler)

    chunks = [c async for c in service.stream(_request())]

    assert len(chunks) == 2
    (obs,) = sink.observations
    assert (obs.mode, obs.outcome, obs.model, obs.finish_reason) == (
        "stream",
        "ok",
        "m",
        "stop",
    )
    assert obs.output_tokens == 3
    assert obs.ttft_s is not None
    assert handler.closed


async def test_stream_failure_is_labelled_error() -> None:
    service, sink = _service(_Handler(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        [c async for c in service.stream(_request())]

    assert [o.outcome for o in sink.observations] == ["error"]


async def test_first_token_timeout() -> None:
    handler = _Handler(5)
    service, sink = _service(handler, first=0.05)

    with pytest.raises(StreamTimeoutError) as caught:
        [c async for c in service.stream(_request())]

    assert (caught.value.code, caught.value.status_code) == ("stream_timeout", 504)
    assert [o.outcome for o in sink.observations] == ["timeout"]
    assert handler.closed


async def test_handler_raised_timeout_is_an_error_not_stream_timeout() -> None:
    service, sink = _service(_Handler(TimeoutError("upstream")))

    with pytest.raises(TimeoutError):
        [c async for c in service.stream(_request())]

    assert [o.outcome for o in sink.observations] == ["error"]


async def test_idle_timeout_after_first_chunk() -> None:
    handler = _Handler(CompletionStreamChunk(delta="a"), 5)
    service, sink = _service(handler, idle=0.05)

    seen = []
    with pytest.raises(StreamTimeoutError):
        async for chunk in service.stream(_request()):
            seen.append(chunk.delta)

    assert seen == ["a"]
    assert [o.outcome for o in sink.observations] == ["timeout"]


async def test_closing_the_stream_early_records_disconnected() -> None:
    handler = _Handler(CompletionStreamChunk(delta="a"), 5)
    service, sink = _service(handler)

    stream = service.stream(_request())
    await anext(stream)
    await stream.aclose()

    assert [o.outcome for o in sink.observations] == ["disconnected"]
    assert handler.closed


def test_log_sink_emits_the_completion_line_and_bound_fields() -> None:
    records: list[dict] = []
    handle = logger.add(lambda m: records.append(m.record), format="{message}")
    try:
        LogCompletionSink().record_completion(
            CompletionObservation(
                mode="stream",
                outcome="ok",
                started_ns=0,
                duration_s=0.0123,
                ttft_s=0.005,
                model="m",
                finish_reason="stop",
                input_tokens=2,
                output_tokens=3,
                total_tokens=5,
            )
        )
    finally:
        logger.remove(handle)

    (record,) = records
    assert record["message"] == (
        "completion mode=stream outcome=ok model=m duration_ms=12.3 ttft_ms=5.0 "
        "finish_reason=stop input_tokens=2 output_tokens=3 total_tokens=5"
    )
    assert record["extra"]["event"] == "completion"
    assert record["extra"]["duration_ms"] == 12.3


def test_fan_out_sink_reaches_every_sink() -> None:
    a, b = _Sink(), _Sink()
    obs = CompletionObservation(
        mode="sync",
        outcome="ok",
        started_ns=0,
        duration_s=0.1,
        ttft_s=None,
        model=None,
        finish_reason=None,
        input_tokens=None,
        output_tokens=None,
    )

    FanOutSink([a, b]).record_completion(obs)

    assert a.observations == [obs] == b.observations
