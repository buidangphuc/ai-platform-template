from langchain_core.tools import StructuredTool
from llama_index.core.schema import NodeWithScore
from pydantic import BaseModel, Field

from app.modules.rag.service import KnowledgeRetrievalService


class KnowledgeSearchInput(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, gt=0)
    filters: dict[str, str | int | float | bool] = Field(default_factory=dict)


def build_knowledge_search_tool(
    knowledge_service: KnowledgeRetrievalService,
) -> StructuredTool:
    async def knowledge_search(
        query: str,
        top_k: int = 5,
        filters: dict[str, str | int | float | bool] | None = None,
    ) -> dict[str, object]:
        response = await knowledge_service.search(
            query,
            top_k=top_k,
            filters=filters or {},
        )
        return {"matches": [_to_tool_match(match) for match in response]}

    return StructuredTool.from_function(
        coroutine=knowledge_search,
        name="knowledge_search",
        description="Search indexed knowledge and return retrieval evidence.",
        args_schema=KnowledgeSearchInput,
    )


def _to_tool_match(match: NodeWithScore) -> dict[str, object]:
    metadata = {
        key: value
        for key, value in match.node.metadata.items()
        if isinstance(value, str | int | float | bool)
    }
    metadata["chunk_id"] = match.node.node_id
    metadata["document_id"] = str(
        metadata.get("document_id") or match.node.ref_doc_id or ""
    )
    return {
        "chunk_id": metadata["chunk_id"],
        "document_id": metadata["document_id"],
        "text": match.node.text or "",
        "score": float(match.score or 0.0),
        "metadata": metadata,
    }
