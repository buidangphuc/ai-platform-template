import asyncio
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass

from app.modules.ai.llm.runtime import StreamTimeoutError
from app.modules.business.completions.guards import CompletionGuard
from app.modules.business.completions.ports import CompletionHandler
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)


@dataclass(frozen=True)
class StreamPolicy:
    first_token_timeout: float
    idle_timeout: float


# Matches the STREAM_*_TIMEOUT_SECONDS defaults; bootstrap passes the configured policy.
DEFAULT_POLICY = StreamPolicy(first_token_timeout=30, idle_timeout=30)


class CompletionService:
    """Completion business service; behavior lives in the injected handler.

    The completions feature builds exactly one instance per app, after resources
    open, and registers it on ``ApplicationResources.services``. The API and the
    worker share it. It does not observe calls: ``LLMInstance`` records one
    ``LlmObservation`` per model call.

    ``guards`` run in order, fail-closed: input guards before the handler, output
    guards on the handler's result. ``stream`` runs input guards only; output
    guards on streamed chunks are not applied yet. ``policy`` bounds how long
    ``stream`` waits for the first chunk and between chunks; a missed deadline
    raises ``StreamTimeoutError``. A failure raised before the first chunk
    surfaces on first iteration, so the API can still answer with a JSON error.
    A handler that sets ``enforces_stream_policy`` (``LlmCompletionHandler``)
    enforces the deadlines itself, so the model call records the timeout; the
    service then waits without its own deadline.
    """

    def __init__(
        self,
        handler: CompletionHandler,
        *,
        guards: Sequence[CompletionGuard] = (),
        policy: StreamPolicy = DEFAULT_POLICY,
    ) -> None:
        self.handler = handler
        self.guards = tuple(guards)
        self.policy = policy

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
        chunks = self.handler.stream(request)
        try:
            await self._check_input(request)
            enforced = getattr(self.handler, "enforces_stream_policy", False)
            deadline = None if enforced else self.policy.first_token_timeout
            while True:
                try:
                    async with asyncio.timeout(deadline) as scope:
                        chunk = await anext(chunks, None)
                except TimeoutError:
                    if scope.expired():
                        raise StreamTimeoutError from None
                    raise
                if chunk is None:
                    break
                deadline = None if enforced else self.policy.idle_timeout
                yield chunk
        finally:
            await chunks.aclose()

    async def _check_input(self, request: CompletionRequest) -> None:
        for guard in self.guards:
            await guard.check_input(request)
