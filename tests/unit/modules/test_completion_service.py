from collections.abc import AsyncIterator

import pytest

from app.modules.business.completions.guards import (
    OUTPUT_VIOLATION_CODE,
    GuardrailViolation,
)
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from app.modules.business.completions.service import CompletionService


class _RecordingCompletionHandler:
    def __init__(self) -> None:
        self.completed: list[CompletionRequest] = []
        self.streamed: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.completed.append(request)
        return CompletionResult(content="done", model="unit")

    async def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[CompletionStreamChunk]:
        self.streamed.append(request)
        yield CompletionStreamChunk(delta="part")


def _request() -> CompletionRequest:
    return CompletionRequest(messages=[{"role": "user", "content": "hello"}])


async def test_completion_service_delegates_complete_to_handler():
    handler = _RecordingCompletionHandler()
    service = CompletionService(handler)

    result = await service.complete(_request())

    assert result.content == "done"
    assert handler.completed[0].messages[-1].content == "hello"


async def test_completion_service_delegates_stream_to_handler():
    handler = _RecordingCompletionHandler()
    service = CompletionService(handler)

    chunks = [chunk async for chunk in service.stream(_request())]

    assert chunks == [CompletionStreamChunk(delta="part")]
    assert handler.streamed[0].messages[-1].content == "hello"


class _Guard:
    def __init__(self, *, block_input: bool = False, block_output: bool = False):
        self.block_input = block_input
        self.block_output = block_output
        self.calls: list[str] = []

    async def check_input(self, request: CompletionRequest) -> None:
        self.calls.append("input")
        if self.block_input:
            raise GuardrailViolation("input blocked")

    async def check_output(
        self, request: CompletionRequest, result: CompletionResult
    ) -> None:
        self.calls.append("output")
        if self.block_output:
            raise GuardrailViolation("output blocked", code=OUTPUT_VIOLATION_CODE)


async def test_guards_run_input_then_handler_then_output():
    handler = _RecordingCompletionHandler()
    guard = _Guard()
    service = CompletionService(handler, guards=(guard,))

    result = await service.complete(_request())

    assert result.content == "done"
    assert guard.calls == ["input", "output"]


async def test_input_violation_blocks_before_handler_runs():
    handler = _RecordingCompletionHandler()
    service = CompletionService(handler, guards=(_Guard(block_input=True),))

    with pytest.raises(GuardrailViolation) as caught:
        await service.complete(_request())

    assert handler.completed == []
    assert caught.value.status_code == 422
    assert caught.value.code == "guardrail_input_violation"


async def test_output_violation_withholds_the_result():
    service = CompletionService(
        _RecordingCompletionHandler(), guards=(_Guard(block_output=True),)
    )

    with pytest.raises(GuardrailViolation) as caught:
        await service.complete(_request())

    assert caught.value.code == "guardrail_output_violation"


async def test_guard_crash_fails_closed():
    class _Broken(_Guard):
        async def check_input(self, request: CompletionRequest) -> None:
            raise RuntimeError("classifier down")

    handler = _RecordingCompletionHandler()
    service = CompletionService(handler, guards=(_Broken(),))

    with pytest.raises(RuntimeError):
        await service.complete(_request())

    assert handler.completed == []


async def test_stream_runs_input_guard_before_streaming():
    handler = _RecordingCompletionHandler()
    service = CompletionService(handler, guards=(_Guard(block_input=True),))

    with pytest.raises(GuardrailViolation):
        _ = [chunk async for chunk in service.stream(_request())]

    assert handler.streamed == []


async def test_stream_applies_no_output_guard_yet():
    guard = _Guard(block_output=True)
    service = CompletionService(_RecordingCompletionHandler(), guards=(guard,))

    chunks = [chunk async for chunk in service.stream(_request())]

    assert chunks == [CompletionStreamChunk(delta="part")]
    assert guard.calls == ["input"]


async def test_echo_stream_yields_one_chunk_carrying_usage_and_finish_reason():
    from app.modules.business.completions.handlers.echo import EchoCompletionHandler

    chunks = [chunk async for chunk in EchoCompletionHandler().stream(_request())]

    assert len(chunks) == 1
    assert chunks[0].delta == "echo: hello"
    assert chunks[0].model == "echo"
    assert chunks[0].finish_reason == "stop"
    assert chunks[0].usage is not None and chunks[0].usage.total_tokens == 3
