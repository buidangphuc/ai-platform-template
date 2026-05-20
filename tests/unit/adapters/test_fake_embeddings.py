from app.adapters.embeddings.fake import FakeEmbeddingClient
from app.contracts.embeddings import EmbeddingClient, EmbeddingRequest


async def test_fake_embeddings_are_deterministic_per_text():
    client: EmbeddingClient = FakeEmbeddingClient(model="fake-embedding", dimensions=8)

    response = await client.embed(
        EmbeddingRequest(texts=["alpha", "alpha", "beta"]),
    )

    assert response.model == "fake-embedding"
    assert len(response.vectors) == 3
    assert len(response.vectors[0]) == 8
    assert response.vectors[0] == response.vectors[1]
    assert response.vectors[0] != response.vectors[2]
    assert response.usage.input_tokens > 0


async def test_fake_embeddings_can_override_dimensions_per_request():
    client = FakeEmbeddingClient(model="fake-embedding", dimensions=8)

    response = await client.embed(
        EmbeddingRequest(texts=["alpha"], dimensions=4),
    )

    assert len(response.vectors[0]) == 4
