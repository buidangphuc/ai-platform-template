from app.contracts.embeddings import EmbeddingClient, EmbeddingRequest
from app.modules.rag.schemas import RagChunk


async def embed_chunks(
    embeddings: EmbeddingClient,
    chunks: list[RagChunk],
) -> list[list[float]]:
    if not chunks:
        return []
    response = await embeddings.embed(
        EmbeddingRequest(texts=[chunk.text for chunk in chunks])
    )
    return response.vectors
