from collections.abc import AsyncGenerator, Sequence

from app.modules.business.completions.guards import CompletionGuard
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

    ``guards`` run in order, fail-closed: input guards before the handler, output
    guards on the handler's result. ``stream`` runs input guards only; output
    guards on streamed chunks are not applied yet. A violation raised by
    ``stream`` surfaces on first iteration; the API layer awaits the first chunk
    before it sends SSE headers, so it still becomes a normal JSON error.
    """

    def __init__(
        self,
        handler: CompletionHandler,
        guards: Sequence[CompletionGuard] = (),
    ) -> None:
        self.handler = handler
        self.guards = tuple(guards)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        await self._check_input(request)
        result = await self.handler.complete(request)
        for guard in self.guards:
            await guard.check_output(request, result)
        return result

    async def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncGenerator[CompletionStreamChunk, None]:
        await self._check_input(request)
        async for chunk in self.handler.stream(request):
            yield chunk

    async def _check_input(self, request: CompletionRequest) -> None:
        for guard in self.guards:
            await guard.check_input(request)
