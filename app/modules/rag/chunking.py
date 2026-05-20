from app.modules.rag.schemas import RagChunk


class TextChunker:
    def __init__(self, *, chunk_size: int = 512, overlap: int = 64) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be non-negative and smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_document(
        self,
        *,
        document_id: str,
        text: str,
        metadata: dict[str, object] | None = None,
    ) -> list[RagChunk]:
        words = text.split()
        if not words:
            return []

        chunks: list[RagChunk] = []
        start = 0
        chunk_index = 0
        while start < len(words):
            end = min(start + self.chunk_size, len(words))
            if start > 0 and end - start <= self.overlap:
                break
            chunk_metadata = dict(metadata or {})
            chunk_metadata.update(
                {
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                }
            )
            chunks.append(
                RagChunk(
                    id=f"{document_id}:chunk:{chunk_index}",
                    document_id=document_id,
                    text=" ".join(words[start:end]),
                    metadata=chunk_metadata,
                )
            )
            if end == len(words):
                break
            start = end - self.overlap
            chunk_index += 1
        return chunks
