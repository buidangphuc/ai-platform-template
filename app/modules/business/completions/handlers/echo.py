from collections.abc import AsyncGenerator

from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
    CompletionUsage,
)


class EchoCompletionHandler:
    """Placeholder handler that echoes the last user message."""

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        last = request.messages[-1].content
        content = f"echo: {last}"
        # Whitespace tokens: a stand-in so the usage contract is exercised end to end.
        input_tokens = sum(len(m.content.split()) for m in request.messages)
        output_tokens = len(content.split())
        return CompletionResult(
            content=content,
            model="echo",
            usage=CompletionUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            finish_reason="stop",
        )

    async def stream(
        self, request: CompletionRequest
    ) -> AsyncGenerator[CompletionStreamChunk, None]:
        result = await self.complete(request)
        yield CompletionStreamChunk(
            delta=result.content,
            model=result.model,
            usage=result.usage,
            finish_reason=result.finish_reason,
        )
