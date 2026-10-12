from collections.abc import AsyncGenerator
from typing import Protocol

from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)


class CompletionHandler(Protocol):
    async def complete(self, request: CompletionRequest) -> CompletionResult: ...

    def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncGenerator[CompletionStreamChunk, None]: ...
