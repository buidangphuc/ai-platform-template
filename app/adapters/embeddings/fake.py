import hashlib

from app.contracts.embeddings import EmbeddingRequest, EmbeddingResponse, EmbeddingUsage


class FakeEmbeddingClient:
    def __init__(self, *, model: str = "fake-embedding", dimensions: int = 16) -> None:
        self.model = model
        self.dimensions = dimensions

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        dimensions = request.dimensions or self.dimensions
        vectors = [self._vector_for_text(text, dimensions) for text in request.texts]
        input_tokens = sum(max(1, len(text.split())) for text in request.texts)
        return EmbeddingResponse(
            vectors=vectors,
            model=request.model or self.model,
            usage=EmbeddingUsage(
                input_tokens=input_tokens,
                total_tokens=input_tokens,
            ),
        )

    def _vector_for_text(self, text: str, dimensions: int) -> list[float]:
        vector: list[float] = []
        counter = 0
        while len(vector) < dimensions:
            digest = hashlib.sha256(f"{text}:{counter}".encode("utf-8")).digest()
            vector.extend((byte / 127.5) - 1.0 for byte in digest)
            counter += 1
        return vector[:dimensions]
