from collections.abc import AsyncIterator

from app.modules.business.completions.pipeline import CompletionPipeline
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)


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


async def test_completion_pipeline_delegates_complete_to_handler():
    handler = _RecordingCompletionHandler()
    pipeline = CompletionPipeline(handler)

    result = await pipeline.complete(_request())

    assert result.content == "done"
    assert handler.completed[0].messages[-1].content == "hello"


async def test_completion_pipeline_delegates_stream_to_handler():
    handler = _RecordingCompletionHandler()
    pipeline = CompletionPipeline(handler)

    chunks = [chunk async for chunk in pipeline.stream(_request())]

    assert chunks == [CompletionStreamChunk(delta="part")]
    assert handler.streamed[0].messages[-1].content == "hello"
