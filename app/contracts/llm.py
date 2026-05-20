from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

MessageRole = Literal["system", "user", "assistant", "tool"]


class LLMToolCall(BaseModel):
    id: str
    type: str = "function"
    name: str
    arguments: str = ""


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @model_validator(mode="after")
    def fill_total_tokens(self) -> "TokenUsage":
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens
        return self


class LLMCacheOptions(BaseModel):
    bypass: bool = False
    scope: str | None = None


class LLMRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list[dict[str, object]] = Field(default_factory=list)
    prompt_version: str | None = None
    tenant_id: str | None = None
    user_id: str | None = None
    safety_settings: dict[str, object] = Field(default_factory=dict)
    cache: LLMCacheOptions = Field(default_factory=LLMCacheOptions)
    metadata: dict[str, str] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    model: str
    finish_reason: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


@runtime_checkable
class LLMClient(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
