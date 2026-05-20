from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator


class EmbeddingUsage(BaseModel):
    input_tokens: int = 0
    total_tokens: int = 0


class EmbeddingRequest(BaseModel):
    texts: list[str] = Field(min_length=1)
    model: str | None = None
    dimensions: int | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("dimensions must be positive")
        return value


class EmbeddingResponse(BaseModel):
    vectors: list[list[float]]
    model: str
    usage: EmbeddingUsage = Field(default_factory=EmbeddingUsage)
    metadata: dict[str, object] = Field(default_factory=dict)


@runtime_checkable
class EmbeddingClient(Protocol):
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise NotImplementedError
