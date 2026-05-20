from langchain_core.embeddings import Embeddings

from app.contracts.vector_store import VectorSearchQuery, VectorStore
from app.modules.rag.schemas import RagSearchMatch, RagSearchResponse


class VectorRagRetriever:
    def __init__(
        self,
        *,
        embeddings: Embeddings,
        vector_store: VectorStore,
    ) -> None:
        self.embeddings = embeddings
        self.vector_store = vector_store

    async def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: dict[str, str | int | float | bool] | None = None,
    ) -> RagSearchResponse:
        embedded_query = await self.embeddings.aembed_query(query)
        matches = await self.vector_store.search(
            VectorSearchQuery(
                vector=embedded_query,
                top_k=top_k,
                filters=filters or {},
            )
        )
        return RagSearchResponse(
            matches=[
                RagSearchMatch(
                    chunk_id=match.document.id,
                    document_id=str(match.document.metadata.get("document_id", "")),
                    text=match.document.text or "",
                    score=match.score,
                    metadata=match.document.metadata,
                )
                for match in matches
            ]
        )
