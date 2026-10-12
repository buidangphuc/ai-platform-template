import json
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Clients speak as the user or replay assistant turns. The system prompt is owned
# by the server (handler/factory); accepting ``system`` here would be direct
# prompt injection by design.
CompletionRole = Literal["user", "assistant"]

MAX_MESSAGES = 64
MAX_MESSAGE_CHARS = 32_000
MAX_METADATA_KEYS = 32
MAX_METADATA_BYTES = 4_096


class CompletionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: CompletionRole
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[CompletionMessage] = Field(min_length=1, max_length=MAX_MESSAGES)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _bound_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > MAX_METADATA_KEYS:
            raise ValueError(f"metadata allows at most {MAX_METADATA_KEYS} keys")
        if len(json.dumps(value, default=str)) > MAX_METADATA_BYTES:
            raise ValueError(
                f"metadata serializes to more than {MAX_METADATA_BYTES} bytes"
            )
        return value


class CompletionUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class StreamSummary(BaseModel):
    """What a stream reports about itself: the latest non-empty value of each field."""

    model: str | None = None
    usage: CompletionUsage | None = None
    finish_reason: str | None = None

    def merge(self, chunk: "CompletionStreamChunk | CompletionResult") -> None:
        self.model = chunk.model or self.model
        self.usage = chunk.usage or self.usage
        self.finish_reason = chunk.finish_reason or self.finish_reason


class CompletionResult(BaseModel):
    content: str
    model: str | None = None
    usage: CompletionUsage | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"cmpl_{uuid4().hex}")
    object: Literal["completion"] = "completion"
    content: str
    model: str | None = None
    usage: CompletionUsage | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionStreamChunk(BaseModel):
    """One streamed piece. The last chunk may carry ``usage``/``finish_reason``."""

    delta: str
    model: str | None = None
    usage: CompletionUsage | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# The task type the completions API submits and the worker runs.
COMPLETION_TASK_TYPE = "completion"
