import asyncio
from collections.abc import Sequence
from typing import Any

from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, NodeWithScore
from llama_index.core.vector_stores.types import (
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)
from loguru import logger

from app.core.redaction import RedactionPolicy
from app.core.resilience import TimeoutPolicy


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
        redaction_policy: RedactionPolicy,
        storage_context: StorageContext | None = None,
        default_top_k: int = 5,
        retrieve_timeout: TimeoutPolicy | None = None,
    ) -> None:
        self.embed_model = embed_model
        self.node_parser = node_parser
        self.redaction_policy = redaction_policy
        self.storage_context = storage_context or StorageContext.from_defaults()
        self.default_top_k = default_top_k
        self.retrieve_timeout = retrieve_timeout
        self.index_store = VectorStoreIndex(
            nodes=[],
            storage_context=self.storage_context,
            embed_model=self.embed_model,
        )
        self._lock = asyncio.Lock()

    async def index(self, documents: Sequence[Document]) -> dict[str, int]:
        if not documents:
            return {"indexed_count": 0, "chunk_count": 0}

        async with self._lock:
            chunk_total = 0
            for raw_doc in documents:
                doc = self._redact_document(raw_doc)
                chunks = await asyncio.to_thread(
                    self.node_parser.get_nodes_from_documents, [doc]
                )
                await asyncio.to_thread(self.index_store.insert_nodes, chunks)
                chunk_total += len(chunks)
            return {"indexed_count": len(documents), "chunk_count": chunk_total}

    async def delete(self, document_id: str) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self.index_store.delete_ref_doc,
                document_id,
                delete_from_docstore=True,
            )

    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: dict[str, str | int | float | bool] | None = None,
    ) -> list[NodeWithScore]:
        retriever = self.index_store.as_retriever(
            similarity_top_k=top_k or self.default_top_k,
            filters=self._build_filters(filters),
        )
        if self.retrieve_timeout is None:
            return await retriever.aretrieve(query)
        return await asyncio.wait_for(
            retriever.aretrieve(query),
            timeout=self.retrieve_timeout.timeout_seconds,
        )

    def _build_filters(
        self,
        filters: dict[str, str | int | float | bool] | None,
    ) -> MetadataFilters | None:
        if not filters:
            return None
        return MetadataFilters(
            filters=[
                MetadataFilter(key=key, value=value, operator=FilterOperator.EQ)
                for key, value in filters.items()
            ]
        )

    def _redact_document(self, document: Document) -> Document:
        metadata = self._redact_metadata(document.metadata)
        metadata["document_id"] = document.id_
        return Document(
            text=self.redaction_policy.redact_text(document.text),
            id_=document.id_,
            metadata=metadata,
        )

    def _redact_metadata(
        self,
        metadata: dict[str, Any],
    ) -> dict[str, str | int | float | bool]:
        redacted = self.redaction_policy.redact_mapping(metadata)
        result: dict[str, str | int | float | bool] = {}
        dropped: list[str] = []
        for key, value in redacted.items():
            if isinstance(value, str | int | float | bool):
                result[key] = value
            else:
                dropped.append(key)
        if dropped:
            logger.warning("rag.metadata.dropped_non_primitive_keys keys={}", dropped)
        return result
