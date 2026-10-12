"""A client disconnect cancels the response under an anyio cancel scope.

Starlette cancels level-triggered: every await in cleanup is cancelled again,
so the completion must still be recorded and the handler must still close.
"""

import asyncio

import anyio
from fastapi import FastAPI, Request

from app.api.sse import event_stream_response
from app.api.v1.completions.router import _events
from app.core.telemetry import CompletionObservation
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from app.modules.business.completions.service import (
    CompletionService,
    StreamPolicy,
)
from tests.factories import build_test_settings


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


class _RecordingSink:
    def __init__(self) -> None:
        self.outcomes: list[str] = []

    def record_completion(self, observation: CompletionObservation) -> None:
        self.outcomes.append(observation.outcome)


async def test_client_disconnect_records_outcome_and_closes_handler() -> None:
    handler = _SlowHandler()
    sink = _RecordingSink()
    service = CompletionService(
        handler,
        sink=sink,
        policy=StreamPolicy(first_token_timeout=5, idle_timeout=30),
    )
    app = FastAPI()
    app.state.settings = build_test_settings()
    response = await event_stream_response(
        Request({"type": "http", "app": app}),
        _events(
            service.stream(
                CompletionRequest(messages=[{"role": "user", "content": "hi"}])
            )
        ),
    )

    with anyio.move_on_after(0.2):
        async for _ in response.body_iterator:
            pass

    assert sink.outcomes == ["disconnected"]
    assert handler.closed is True
