from collections.abc import AsyncIterator
from typing import Protocol

from app.api.v1.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)


class CompletionHandler(Protocol):
    async def complete(self, request: CompletionRequest) -> CompletionResult: ...

    def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncIterator[CompletionStreamChunk | str]: ...
