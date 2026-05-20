import math

from app.contracts.vector_store import (
    VectorDocument,
    VectorSearchMatch,
    VectorSearchQuery,
)


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._documents: dict[str, VectorDocument] = {}

    async def upsert(self, documents: list[VectorDocument]) -> None:
        for document in documents:
            self._documents[document.id] = document.model_copy(deep=True)

    async def search(self, query: VectorSearchQuery) -> list[VectorSearchMatch]:
        matches: list[VectorSearchMatch] = []
        for document in self._documents.values():
            if not self._metadata_matches(document, query):
                continue
            score = self._cosine_similarity(query.vector, document.vector)
            matches.append(
                VectorSearchMatch(
                    document=document.model_copy(deep=True),
                    score=score,
                ),
            )
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[: query.top_k]

    async def delete(self, ids: list[str]) -> None:
        for document_id in ids:
            self._documents.pop(document_id, None)

    def _metadata_matches(
        self,
        document: VectorDocument,
        query: VectorSearchQuery,
    ) -> bool:
        return all(
            document.metadata.get(key) == value for key, value in query.filters.items()
        )

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            raise ValueError("vector dimension mismatch")
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return sum(
            left_value * right_value
            for left_value, right_value in zip(left, right, strict=True)
        ) / (left_norm * right_norm)
