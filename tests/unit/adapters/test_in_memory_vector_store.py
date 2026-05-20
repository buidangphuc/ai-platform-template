import pytest

from app.adapters.vector_store.in_memory import InMemoryVectorStore
from app.contracts.vector_store import VectorDocument, VectorSearchQuery, VectorStore


async def test_in_memory_vector_store_searches_by_cosine_similarity():
    store: VectorStore = InMemoryVectorStore()
    await store.upsert(
        [
            VectorDocument(
                id="doc-a",
                vector=[1.0, 0.0],
                text="alpha",
                metadata={"tenant": "demo"},
            ),
            VectorDocument(
                id="doc-b",
                vector=[0.0, 1.0],
                text="beta",
                metadata={"tenant": "demo"},
            ),
        ],
    )

    matches = await store.search(
        VectorSearchQuery(vector=[0.9, 0.1], top_k=2, filters={"tenant": "demo"}),
    )

    assert [match.document.id for match in matches] == ["doc-a", "doc-b"]
    assert matches[0].score > matches[1].score


async def test_in_memory_vector_store_filters_and_deletes_documents():
    store = InMemoryVectorStore()
    await store.upsert(
        [
            VectorDocument(id="doc-a", vector=[1.0], metadata={"tenant": "a"}),
            VectorDocument(id="doc-b", vector=[1.0], metadata={"tenant": "b"}),
        ],
    )

    only_a = await store.search(
        VectorSearchQuery(vector=[1.0], top_k=10, filters={"tenant": "a"}),
    )
    await store.delete(["doc-a"])
    after_delete = await store.search(VectorSearchQuery(vector=[1.0], top_k=10))

    assert [match.document.id for match in only_a] == ["doc-a"]
    assert [match.document.id for match in after_delete] == ["doc-b"]


async def test_in_memory_vector_store_rejects_dimension_mismatch():
    store = InMemoryVectorStore()
    await store.upsert([VectorDocument(id="doc-a", vector=[1.0, 0.0])])

    with pytest.raises(ValueError, match="dimension"):
        await store.search(VectorSearchQuery(vector=[1.0], top_k=1))
