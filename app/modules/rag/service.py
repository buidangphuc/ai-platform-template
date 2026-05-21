import asyncio
from collections.abc import Sequence
from typing import Any

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, NodeWithScore

from app.core.redaction import RedactionPolicy


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
    ) -> None:
        self.embed_model = embed_model
        self.node_parser = node_parser
        self.redaction_policy = redaction_policy
        self.index_store: VectorStoreIndex | None = None
        self._documents: dict[str, Document] = {}

    async def index(self, documents: Sequence[Document]) -> dict[str, int]:
        if not documents:
            raise ValueError("documents must not be empty")

        documents = [self._redact_document(document) for document in documents]
        for document in documents:
            self._documents[document.id_] = document

        chunks = await asyncio.to_thread(
            self.node_parser.get_nodes_from_documents, documents
        )
        self.index_store = await asyncio.to_thread(
            VectorStoreIndex.from_documents,
            list(self._documents.values()),
            transformations=[self.node_parser],
            embed_model=self.embed_model,
        )
        return {"indexed_count": len(documents), "chunk_count": len(chunks)}

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: dict[str, str | int | float | bool] | None = None,
    ) -> list[NodeWithScore]:
        if self.index_store is None:
            return []

        retriever = self.index_store.as_retriever(
            similarity_top_k=max(top_k, top_k * 4 if filters else top_k),
        )
        retrieved = await retriever.aretrieve(query)
        return [
            node
            for node in retrieved
            if self._matches_filters(node.node.metadata, filters or {})
        ][:top_k]

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
        return {
            key: value
            for key, value in redacted.items()
            if isinstance(value, str | int | float | bool)
        }

    def _matches_filters(
        self,
        metadata: dict[str, Any],
        filters: dict[str, str | int | float | bool],
    ) -> bool:
        return all(metadata.get(key) == value for key, value in filters.items())
