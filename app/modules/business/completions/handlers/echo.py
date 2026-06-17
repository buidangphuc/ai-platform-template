from collections.abc import AsyncIterator

from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)


class EchoCompletionHandler:
    """Placeholder handler that echoes the last user message."""

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        last = request.messages[-1].content
        return CompletionResult(content=f"echo: {last}", model="echo")

    async def stream(
        self, request: CompletionRequest
    ) -> AsyncIterator[CompletionStreamChunk]:  # pragma: no cover
        yield CompletionStreamChunk(delta=f"echo: {request.messages[-1].content}")
