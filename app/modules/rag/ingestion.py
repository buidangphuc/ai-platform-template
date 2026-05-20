from app.contracts.embeddings import EmbeddingClient
from app.contracts.vector_store import VectorDocument, VectorStore
from app.modules.rag.chunking import TextChunker
from app.modules.rag.embeddings import embed_chunks
from app.modules.rag.schemas import RagIndexRequest, RagIndexResponse


class RagIngestionService:
    def __init__(
        self,
        *,
        embeddings: EmbeddingClient,
        vector_store: VectorStore,
        chunker: TextChunker,
    ) -> None:
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.chunker = chunker

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
        vectors = await embed_chunks(self.embeddings, chunks)
        await self.vector_store.upsert(
            [
                VectorDocument(
                    id=chunk.id,
                    vector=vector,
                    text=chunk.text,
                    metadata=chunk.metadata,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
        )
        return RagIndexResponse(
            indexed_count=len(request.documents),
            chunk_count=len(chunks),
        )
