"""Remote embedding seam: the model-server contract + failure modes.

Exercises the pure parser and the sync/async HTTP wrappers with fakes — no
llama-index, no live server, fully offline.
"""

from __future__ import annotations

import pytest

from app.core.errors import ServiceUnavailableError
from app.modules.ai.rag.embeddings import (
    _extract_vectors,
    aembed_texts,
    embed_texts,
)


class _FakeResponse:
    def __init__(self, status_code: int, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response
        self.last = None

    async def post(self, path, json):
        self.last = (path, json)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeSyncClient:
    def __init__(self, response):
        self._response = response
        self.last = None

    def post(self, path, json):
        self.last = (path, json)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


# ── _extract_vectors (pure) ──────────────────────────────────────────────────


def test_extract_embeddings_key():
    data = {"embeddings": [[1.0, 2.0], [3.0, 4.0]]}
    assert _extract_vectors(data, count=2, expected_dim=2) == [[1.0, 2.0], [3.0, 4.0]]


def test_extract_openai_data_shape():
    data = {"data": [{"embedding": [1, 2, 3]}]}
    assert _extract_vectors(data, count=1) == [[1.0, 2.0, 3.0]]


def test_extract_bare_list():
    assert _extract_vectors([[0.5]], count=1) == [[0.5]]


def test_extract_coerces_ints_to_float():
    result = _extract_vectors({"embeddings": [[1, 2]]}, count=1)
    assert result == [[1.0, 2.0]]
    assert all(isinstance(x, float) for x in result[0])


def test_extract_missing_key_raises():
    with pytest.raises(ServiceUnavailableError):
        _extract_vectors({"nope": []}, count=1)


def test_extract_count_mismatch_raises():
    with pytest.raises(ServiceUnavailableError):
        _extract_vectors({"embeddings": [[1.0]]}, count=2)


def test_extract_non_vector_element_raises():
    with pytest.raises(ServiceUnavailableError):
        _extract_vectors({"embeddings": ["not-a-vector"]}, count=1)


def test_extract_non_numeric_raises():
    with pytest.raises(ServiceUnavailableError):
        _extract_vectors({"embeddings": [["a", "b"]]}, count=1)


def test_extract_dim_mismatch_raises():
    with pytest.raises(ServiceUnavailableError) as exc:
        _extract_vectors({"embeddings": [[1.0, 2.0]]}, count=1, expected_dim=3)
    assert exc.value.code == "embedding_server_dim_mismatch"


# ── aembed_texts / embed_texts (HTTP wrappers) ───────────────────────────────


async def test_aembed_happy_path():
    fake = _FakeAsyncClient(_FakeResponse(200, {"embeddings": [[1.0, 2.0]]}))
    vectors = await aembed_texts(fake, ["hello"], path="/embed", expected_dim=2)
    assert vectors == [[1.0, 2.0]]
    assert fake.last == ("/embed", {"texts": ["hello"]})


async def test_aembed_empty_texts_skips_call():
    fake = _FakeAsyncClient(_FakeResponse(500))
    assert await aembed_texts(fake, [], path="/embed") == []
    assert fake.last is None


async def test_aembed_unreachable_raises():
    fake = _FakeAsyncClient(RuntimeError("boom"))
    with pytest.raises(ServiceUnavailableError) as exc:
        await aembed_texts(fake, ["x"], path="/embed")
    assert exc.value.code == "embedding_server_unavailable"


async def test_aembed_non_200_raises():
    fake = _FakeAsyncClient(_FakeResponse(503))
    with pytest.raises(ServiceUnavailableError) as exc:
        await aembed_texts(fake, ["x"], path="/embed")
    assert exc.value.code == "embedding_server_error"


def test_embed_sync_happy_path():
    fake = _FakeSyncClient(_FakeResponse(200, {"embeddings": [[9.0]]}))
    assert embed_texts(fake, ["q"], path="/embed") == [[9.0]]
    assert fake.last == ("/embed", {"texts": ["q"]})
