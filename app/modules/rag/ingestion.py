from app.contracts.embeddings import EmbeddingClient
from app.contracts.vector_store import VectorDocument, VectorStore
from app.core.redaction import RedactionPolicy
from app.modules.rag.chunking import TextChunker
from app.modules.rag.embeddings import embed_chunks
from app.modules.rag.schemas import RagChunk, RagIndexRequest, RagIndexResponse


class RagIngestionService:
    def __init__(
        self,
        *,
        embeddings: EmbeddingClient,
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
        vectors = await embed_chunks(self.embeddings, redacted_chunks)
        await self.vector_store.upsert(
            [
                VectorDocument(
                    id=chunk.id,
                    vector=vector,
                    text=chunk.text,
                    metadata=chunk.metadata,
                )
                for chunk, vector in zip(redacted_chunks, vectors, strict=True)
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
