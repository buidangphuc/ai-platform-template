import time
from typing import Any

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, NodeWithScore

from app.core.redaction import RedactionPolicy
from app.modules.rag.reranking import ScoreReranker
from app.modules.rag.schemas import (
    RagDocument,
    RagIndexRequest,
    RagIndexResponse,
    RagSearchMatch,
    RagSearchRequest,
    RagSearchResponse,
)
from app.modules.usage.schemas import UsageRecord
from app.modules.usage.tracker import InMemoryUsageTracker


def build_rag_node_parser(*, chunk_size: int, chunk_overlap: int) -> SentenceSplitter:
    return SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        id_func=_llamaindex_chunk_id,
    )


def _llamaindex_chunk_id(index: int, document: BaseNode) -> str:
    return f"{document.id_}:chunk:{index}"


class KnowledgeRetrievalService:
    def __init__(
        self,
        *,
        embed_model: BaseEmbedding,
        node_parser: SentenceSplitter,
        usage_tracker: InMemoryUsageTracker,
        redaction_policy: RedactionPolicy,
    ) -> None:
        self.embed_model = embed_model
        self.node_parser = node_parser
        self.usage_tracker = usage_tracker
        self.redaction_policy = redaction_policy
        self.reranker = ScoreReranker()
        self.index_store: VectorStoreIndex | None = None
        self._documents: dict[str, Document] = {}

    async def index(self, request: RagIndexRequest) -> RagIndexResponse:
        started_at = time.perf_counter()
        documents = [
            self._to_llamaindex_document(document) for document in request.documents
        ]
        for document in documents:
            self._documents[document.id_] = document

        chunks = self.node_parser.get_nodes_from_documents(documents)
        self.index_store = VectorStoreIndex.from_documents(
            list(self._documents.values()),
            transformations=[self.node_parser],
            embed_model=self.embed_model,
        )
        await self.usage_tracker.record(
            UsageRecord(
                operation="rag.index",
                provider="llamaindex",
                model=self._embedding_model_name(),
                latency_ms=(time.perf_counter() - started_at) * 1000,
                estimated_cost=0.0,
                metadata={"chunk_count": len(chunks)},
            )
        )
        return RagIndexResponse(
            indexed_count=len(request.documents),
            chunk_count=len(chunks),
        )

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: dict[str, str | int | float | bool] | None = None,
    ) -> RagSearchResponse:
        started_at = time.perf_counter()
        matches: list[RagSearchMatch] = []
        if self.index_store is not None:
            retriever = self.index_store.as_retriever(
                similarity_top_k=max(top_k, top_k * 4 if filters else top_k),
            )
            retrieved = await retriever.aretrieve(query)
            matches = [
                self._search_match(node)
                for node in retrieved
                if self._matches_filters(node.node.metadata, filters or {})
            ][:top_k]

        reranked_matches = self.reranker.rerank(matches)
        await self.usage_tracker.record(
            UsageRecord(
                operation="rag.search",
                provider="llamaindex",
                model=self._embedding_model_name(),
                latency_ms=(time.perf_counter() - started_at) * 1000,
                estimated_cost=0.0,
                metadata={"top_k": top_k, "match_count": len(reranked_matches)},
            )
        )
        return RagSearchResponse(matches=reranked_matches)

    async def search_request(self, request: RagSearchRequest) -> RagSearchResponse:
        return await self.search(
            request.query,
            top_k=request.top_k,
            filters=request.filters,
        )

    def _to_llamaindex_document(self, document: RagDocument) -> Document:
        metadata = self._redact_metadata(document.metadata)
        metadata["document_id"] = document.id
        return Document(
            text=self.redaction_policy.redact_text(document.text),
            id_=document.id,
            metadata=metadata,
        )

    def _redact_metadata(
        self,
        metadata: dict[str, str | int | float | bool],
    ) -> dict[str, str | int | float | bool]:
        redacted = self.redaction_policy.redact_mapping(metadata)
        return {
            key: value
            for key, value in redacted.items()
            if isinstance(value, str | int | float | bool)
        }

    def _search_match(self, node: NodeWithScore) -> RagSearchMatch:
        metadata = self._node_metadata(node.node)
        return RagSearchMatch(
            chunk_id=str(metadata["chunk_id"]),
            document_id=str(metadata["document_id"]),
            text=node.node.text or "",
            score=float(node.score or 0.0),
            metadata=metadata,
        )

    def _node_metadata(
        self,
        node: BaseNode,
    ) -> dict[str, str | int | float | bool]:
        metadata = {
            key: value
            for key, value in node.metadata.items()
            if isinstance(value, str | int | float | bool)
        }
        metadata["chunk_id"] = node.node_id
        metadata["document_id"] = str(
            metadata.get("document_id") or node.ref_doc_id or ""
        )
        return metadata

    def _matches_filters(
        self,
        metadata: dict[str, Any],
        filters: dict[str, str | int | float | bool],
    ) -> bool:
        return all(metadata.get(key) == value for key, value in filters.items())

    def _embedding_model_name(self) -> str:
        return str(
            getattr(self.embed_model, "model_name", type(self.embed_model).__name__)
        )
