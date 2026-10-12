from collections.abc import AsyncIterator

from app.modules.business.completions.ports import CompletionHandler
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)


class CompletionService:
    """Completion business service; behavior lives in the injected handler.

    Bootstrap builds exactly one instance per app, after resources open, and
    stores it on ``ApplicationResources.completion_service``.
    """

    def __init__(self, handler: CompletionHandler) -> None:
        self.handler = handler

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return await self.handler.complete(request)

    def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[CompletionStreamChunk | str]:
        return self.handler.stream(request)
