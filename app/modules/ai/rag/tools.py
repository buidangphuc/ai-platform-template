from langchain_core.tools import StructuredTool
from llama_index.core.schema import NodeWithScore
from pydantic import BaseModel, Field

from app.modules.ai.rag.service import KnowledgeRetrievalService


class KnowledgeSearchInput(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, gt=0)
    filters: dict[str, str | int | float | bool] = Field(default_factory=dict)


class KnowledgeSearchMatch(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    metadata: dict[str, str | int | float | bool]


class KnowledgeSearchResult(BaseModel):
    matches: list[KnowledgeSearchMatch]


def build_knowledge_search_tool(
    knowledge_service: KnowledgeRetrievalService,
) -> StructuredTool:
    async def knowledge_search(
        query: str,
        top_k: int = 5,
        filters: dict[str, str | int | float | bool] | None = None,
    ) -> dict[str, object]:
        nodes = await knowledge_service.search(
            query,
            top_k=top_k,
            filters=filters or {},
        )
        result = KnowledgeSearchResult(matches=[_to_match(node) for node in nodes])
        return result.model_dump()

    return StructuredTool.from_function(
        coroutine=knowledge_search,
        name="knowledge_search",
        description="Search indexed knowledge and return retrieval evidence.",
        args_schema=KnowledgeSearchInput,
    )


def _to_match(match: NodeWithScore) -> KnowledgeSearchMatch:
    metadata = {
        key: value
        for key, value in match.node.metadata.items()
        if isinstance(value, str | int | float | bool)
    }
    chunk_id = match.node.node_id
    document_id = str(metadata.get("document_id") or match.node.ref_doc_id or "")
    metadata["chunk_id"] = chunk_id
    metadata["document_id"] = document_id
    return KnowledgeSearchMatch(
        chunk_id=chunk_id,
        document_id=document_id,
        text=match.node.get_content() or "",
        score=float(match.score or 0.0),
        metadata=metadata,
    )
