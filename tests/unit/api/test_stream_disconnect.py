"""A client disconnect cancels the response under an anyio cancel scope.

Starlette cancels level-triggered: every await in cleanup is cancelled again,
so the completion must still be recorded and the handler must still close.
"""

import asyncio

import anyio

from app.api.v1.completions.observability import CompletionTimer, Outcome
from app.api.v1.completions.streaming import StreamLimits, open_event_stream
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from app.modules.business.completions.service import CompletionService


class _SlowHandler:
    def __init__(self) -> None:
        self.closed = False

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return CompletionResult(content="", model="slow")

    async def stream(self, request: CompletionRequest):
        try:
            yield CompletionStreamChunk(delta="first")
            await asyncio.sleep(30)
            yield CompletionStreamChunk(delta="never")
        finally:
            self.closed = True


class _RecordingTimer(CompletionTimer):
    def __init__(self) -> None:
        super().__init__(mode="stream")
        self.outcomes: list[Outcome] = []

    def emit(self, outcome: Outcome) -> None:
        self.outcomes.append(outcome)


async def test_client_disconnect_records_outcome_and_closes_handler() -> None:
    handler = _SlowHandler()
    timer = _RecordingTimer()
    frames = await open_event_stream(
        CompletionService(handler),
        CompletionRequest(messages=[{"role": "user", "content": "hi"}]),
        StreamLimits(first_token_timeout=5, idle_timeout=30, heartbeat=10),
        timer,
    )

    with anyio.move_on_after(0.2):
        async for _ in frames:
            pass

    assert timer.outcomes == ["disconnected"]
    assert handler.closed is True
