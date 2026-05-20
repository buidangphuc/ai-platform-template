from pydantic import BaseModel, Field


class RagDocument(BaseModel):
    id: str
    text: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RagChunk(BaseModel):
    id: str
    document_id: str
    text: str
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RagIndexRequest(BaseModel):
    documents: list[RagDocument] = Field(min_length=1)


class RagIndexResponse(BaseModel):
    indexed_count: int
    chunk_count: int


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, gt=0)
    filters: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RagSearchMatch(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RagSearchResponse(BaseModel):
    matches: list[RagSearchMatch]
