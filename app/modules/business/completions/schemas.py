from typing import Any, Literal

from pydantic import BaseModel, Field

CompletionRole = Literal["system", "user", "assistant"]


class CompletionMessage(BaseModel):
    role: CompletionRole
    content: str = Field(min_length=1)


class CompletionRequest(BaseModel):
    messages: list[CompletionMessage] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionResult(BaseModel):
    content: str
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionResponse(BaseModel):
    id: str
    object: Literal["completion"] = "completion"
    content: str
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionStreamChunk(BaseModel):
    delta: str
    metadata: dict[str, Any] = Field(default_factory=dict)
