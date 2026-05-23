from collections.abc import AsyncIterator

from app.modules.business.completions.ports import CompletionHandler
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)


class CompletionPipeline:
    def __init__(self, handler: CompletionHandler) -> None:
        self.handler = handler

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return await self.handler.complete(request)

    def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[CompletionStreamChunk | str]:
        return self.handler.stream(request)
