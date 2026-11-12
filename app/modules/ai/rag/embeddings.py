"""Remote embeddings for RAG: vectorization is delegated to an embedding server.

The API process runs no embedding model. With ``RAG_EMBED_BACKEND=model_server``
every text is embedded by an HTTP server through an ``UpstreamClient``, so the
timeout, retry, circuit breaker and ``X-Request-ID`` propagation come from it.

Wire contract::

    POST {RAG_EMBED_SERVER_PATH}  {"texts": ["a", "b"]}

Accepted replies, first match wins (the second is the OpenAI embeddings shape)::

    {"embeddings": [[...], [...]]}
    {"data": [{"embedding": [...]}, {"embedding": [...]}]}
    [[...], [...]]

The reply must hold exactly one non-empty numeric vector per text, each of
length ``RAG_EMBED_DIM``. Anything else raises ``ServiceUnavailableError``
(``embedding_server_bad_response`` or ``embedding_server_dim_mismatch``), as do
a non-200 reply (``embedding_server_error``) and a transport failure
(``embedding_server_unavailable``): a partial or wrong-sized vector is never
returned, so it is never indexed.

LlamaIndex indexing (``ainsert_nodes``) and retrieval (``aretrieve``) only call
the async embedding methods; the sync ones raise ``RuntimeError``.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from app.core.errors import ServiceUnavailableError
from app.modules.platform.http.upstream import UpstreamClient

if TYPE_CHECKING:
    from llama_index.core.base.embeddings.base import BaseEmbedding

Vector = list[float]


@runtime_checkable
class SupportsAclose(Protocol):
    async def aclose(self) -> None: ...


def _bad_response(message: str) -> ServiceUnavailableError:
    return ServiceUnavailableError(
        message=message, code="embedding_server_bad_response"
    )


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def parse_embedding_reply(data: Any, *, count: int, dim: int) -> list[Vector]:
    """Validate an embedding server reply into ``count`` vectors of length ``dim``."""
    raw: Any
    if isinstance(data, dict):
        if "embeddings" in data:
            raw = data["embeddings"]
        elif "data" in data and isinstance(data["data"], list):
            raw = [
                item.get("embedding") if isinstance(item, dict) else None
                for item in data["data"]
            ]
        else:
            raise _bad_response("Embedding server reply has no embeddings")
    elif isinstance(data, list):
        raw = data
    else:
        raise _bad_response(
            f"Embedding server reply has unexpected type {type(data).__name__}"
        )

    if not isinstance(raw, list) or len(raw) != count:
        received = len(raw) if isinstance(raw, list) else "no"
        raise _bad_response(
            f"Embedding server returned {received} vectors, expected {count}"
        )

    vectors: list[Vector] = []
    for item in raw:
        if not isinstance(item, list) or not item:
            raise _bad_response("Embedding server returned a non-vector element")
        if not all(_is_number(value) for value in item):
            raise _bad_response("Embedding vector contains non-numeric values")
        if len(item) != dim:
            raise ServiceUnavailableError(
                message=f"Embedding dimension {len(item)} != expected {dim}",
                code="embedding_server_dim_mismatch",
            )
        vectors.append([float(value) for value in item])
    return vectors


def build_model_server_embedding(
    client: UpstreamClient, *, path: str, dim: int
) -> BaseEmbedding:
    """LlamaIndex embedding that POSTs texts to the server behind ``client``.

    The returned object owns ``client``: ``await embedding.aclose()`` closes it.
    """
    from llama_index.core.base.embeddings.base import BaseEmbedding
    from pydantic import PrivateAttr

    class ModelServerEmbedding(BaseEmbedding):
        _client: UpstreamClient = PrivateAttr()
        _path: str = PrivateAttr()
        _dim: int = PrivateAttr()

        def __init__(self) -> None:
            super().__init__(model_name="model_server")
            self._client = client
            self._path = path
            self._dim = dim

        @classmethod
        def class_name(cls) -> str:
            return "ModelServerEmbedding"

        async def _embed(self, texts: list[str]) -> list[Vector]:
            if not texts:
                return []
            try:
                response = await self._client.post(self._path, json={"texts": texts})
            except Exception as exc:
                raise ServiceUnavailableError(
                    message="Embedding server is unreachable",
                    code="embedding_server_unavailable",
                ) from exc
            if response.status_code != 200:
                raise ServiceUnavailableError(
                    message=f"Embedding server returned {response.status_code}",
                    code="embedding_server_error",
                )
            try:
                reply = response.json()
            except ValueError as exc:
                raise _bad_response("Embedding server reply is not JSON") from exc
            return parse_embedding_reply(reply, count=len(texts), dim=self._dim)

        async def _aget_text_embeddings(self, texts: list[str]) -> list[Vector]:
            return await self._embed(texts)

        async def _aget_text_embedding(self, text: str) -> Vector:
            return (await self._embed([text]))[0]

        async def _aget_query_embedding(self, query: str) -> Vector:
            return (await self._embed([query]))[0]

        def _get_text_embeddings(self, texts: list[str]) -> list[Vector]:
            raise _async_only("aget_text_embedding_batch")

        def _get_text_embedding(self, text: str) -> Vector:
            raise _async_only("aget_text_embedding")

        def _get_query_embedding(self, query: str) -> Vector:
            raise _async_only("aget_query_embedding")

        async def aclose(self) -> None:
            await self._client.aclose()

    return ModelServerEmbedding()


def _async_only(method: str) -> RuntimeError:
    return RuntimeError(
        f"ModelServerEmbedding is async-only: call {method} instead of the sync method"
    )
