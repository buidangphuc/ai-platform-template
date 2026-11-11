from collections.abc import AsyncGenerator, Sequence
from typing import Any

from app.modules.ai._deps import require_langchain
from app.modules.ai.llm.runtime import LLMInstance
from app.modules.business.completions.schemas import (
    CompletionMessage,
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
    CompletionUsage,
)
from app.modules.business.completions.service import DEFAULT_POLICY, StreamPolicy


def _to_messages(messages: Sequence[CompletionMessage]) -> list[Any]:
    require_langchain()
    from langchain_core.messages import AIMessage, HumanMessage

    return [
        HumanMessage(content=m.content)
        if m.role == "user"
        else AIMessage(content=m.content)
        for m in messages
    ]


def _usage(metadata: Any) -> CompletionUsage | None:
    if not metadata:
        return None
    input_tokens = int(metadata.get("input_tokens", 0))
    output_tokens = int(metadata.get("output_tokens", 0))
    return CompletionUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=int(metadata.get("total_tokens", input_tokens + output_tokens)),
    )


def _model_name(response_metadata: dict[str, Any]) -> str | None:
    return response_metadata.get("model_name") or response_metadata.get("model")


class LlmCompletionHandler:
    """Answers completions by calling the shared ``LLMInstance``."""

    enforces_stream_policy = True

    def __init__(self, llm: LLMInstance, policy: StreamPolicy = DEFAULT_POLICY) -> None:
        self.llm = llm
        self.policy = policy

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        message = await self.llm.ainvoke(_to_messages(request.messages))
        return CompletionResult(
            content=str(message.text),
            model=_model_name(message.response_metadata),
            usage=_usage(getattr(message, "usage_metadata", None)),
            finish_reason=message.response_metadata.get("finish_reason"),
        )

    async def stream(
        self, request: CompletionRequest
    ) -> AsyncGenerator[CompletionStreamChunk, None]:
        async for chunk in self.llm.astream(
            _to_messages(request.messages),
            first_token_timeout=self.policy.first_token_timeout,
            idle_timeout=self.policy.idle_timeout,
        ):
            yield CompletionStreamChunk(
                delta=str(chunk.text),
                model=_model_name(chunk.response_metadata),
                usage=_usage(getattr(chunk, "usage_metadata", None)),
                finish_reason=chunk.response_metadata.get("finish_reason"),
            )
