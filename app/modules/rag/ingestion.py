from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.contracts.vector_store import VectorDocument, VectorStore
from app.core.redaction import RedactionPolicy
from app.modules.rag.chunking import TextChunker
from app.modules.rag.embeddings import embed_documents
from app.modules.rag.schemas import RagChunk, RagIndexRequest, RagIndexResponse


class RagIngestionService:
    def __init__(
        self,
        *,
        embeddings: Embeddings,
        vector_store: VectorStore,
        chunker: TextChunker,
        redaction_policy: RedactionPolicy,
    ) -> None:
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.chunker = chunker
        self.redaction_policy = redaction_policy

    async def index(self, request: RagIndexRequest) -> RagIndexResponse:
        chunks = [
            chunk
            for document in request.documents
            for chunk in self.chunker.chunk_document(
                document_id=document.id,
                text=document.text,
                metadata=document.metadata,
            )
        ]
        redacted_chunks = [self._redact_chunk(chunk) for chunk in chunks]
        documents = [self._chunk_to_document(chunk) for chunk in redacted_chunks]
        vectors = await embed_documents(self.embeddings, documents)
        await self.vector_store.upsert(
            [
                VectorDocument(
                    id=str(document.metadata["chunk_id"]),
                    vector=vector,
                    text=document.page_content,
                    metadata=self._vector_metadata(document.metadata),
                )
                for document, vector in zip(documents, vectors, strict=True)
            ]
        )
        return RagIndexResponse(
            indexed_count=len(request.documents),
            chunk_count=len(chunks),
        )

    def _redact_chunk(self, chunk: RagChunk) -> RagChunk:
        return chunk.model_copy(
            update={
                "text": self.redaction_policy.redact_text(chunk.text),
                "metadata": self._redact_metadata(chunk.metadata),
            }
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

    def _chunk_to_document(self, chunk: RagChunk) -> Document:
        metadata = dict(chunk.metadata)
        metadata.update(
            {
                "document_id": chunk.document_id,
                "chunk_id": chunk.id,
            }
        )
        return Document(page_content=chunk.text, metadata=metadata)

    def _vector_metadata(
        self,
        metadata: dict[str, object],
    ) -> dict[str, str | int | float | bool]:
        return {
            key: value
            for key, value in metadata.items()
            if isinstance(value, str | int | float | bool)
        }
