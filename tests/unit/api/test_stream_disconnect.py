"""A client disconnect cancels the response under an anyio cancel scope.

Starlette cancels level-triggered: every await in cleanup is cancelled again,
so the LLM call must still be recorded and the model stream must still close.
"""

import asyncio

import anyio
from fastapi import FastAPI, Request
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from pydantic import Field

from app.api.sse import event_stream_response
from app.api.v1.completions.router import _events
from app.core.telemetry import LlmObservation
from app.modules.ai.llm.runtime import build_llm_instance
from app.modules.business.completions.handlers.llm import LlmCompletionHandler
from app.modules.business.completions.schemas import CompletionRequest
from app.modules.business.completions.service import (
    CompletionService,
    StreamPolicy,
)
from tests.factories import build_test_settings


class _SlowModel(FakeListChatModel):
    closed: list[bool] = Field(default_factory=list)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            yield ChatGenerationChunk(message=AIMessageChunk(content="first"))
            await asyncio.sleep(30)
            yield ChatGenerationChunk(message=AIMessageChunk(content="never"))
        finally:
            self.closed.append(True)


class _RecordingSink:
    def __init__(self) -> None:
        self.outcomes: list[str] = []

    def record_llm(self, observation: LlmObservation) -> None:
        self.outcomes.append(observation.outcome)


async def test_client_disconnect_records_outcome_and_closes_model_stream() -> None:
    model = _SlowModel(responses=["x"], closed=[])
    sink = _RecordingSink()
    llm = build_llm_instance(
        build_test_settings(CHAT_MODEL="m"),
        instance_id="t",
        service_name="test",
        model_builder=lambda target: model,
        sink=sink,
    )
    service = CompletionService(
        LlmCompletionHandler(llm),
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
    assert model.closed == [True]
