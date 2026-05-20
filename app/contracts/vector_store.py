from typing import Protocol, TypeAlias, runtime_checkable

from pydantic import BaseModel, Field

MetadataValue: TypeAlias = str | int | float | bool


class VectorDocument(BaseModel):
    id: str
    vector: list[float] = Field(min_length=1)
    text: str | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class VectorSearchQuery(BaseModel):
    vector: list[float] = Field(min_length=1)
    top_k: int = Field(default=5, gt=0)
    filters: dict[str, MetadataValue] = Field(default_factory=dict)


class VectorSearchMatch(BaseModel):
    document: VectorDocument
    score: float


@runtime_checkable
class VectorStore(Protocol):
    async def upsert(self, documents: list[VectorDocument]) -> None:
        raise NotImplementedError

    async def search(self, query: VectorSearchQuery) -> list[VectorSearchMatch]:
        raise NotImplementedError

    async def delete(self, ids: list[str]) -> None:
        raise NotImplementedError
