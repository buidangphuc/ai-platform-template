from langchain_core.tools import StructuredTool
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
        return {
            "matches": [
                {
                    "chunk_id": match.chunk_id,
                    "document_id": match.document_id,
                    "text": match.text,
                    "score": match.score,
                    "metadata": match.metadata,
                }
                for match in response.matches
            ]
        }

    return StructuredTool.from_function(
        coroutine=knowledge_search,
        name="knowledge_search",
        description="Search indexed knowledge and return retrieval evidence.",
        args_schema=KnowledgeSearchInput,
    )
