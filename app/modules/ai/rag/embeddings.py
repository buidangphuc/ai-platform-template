"""Remote embedding adapter — the ML/LLM decoupling seam for team-ai.

team-ai runs NO embedding model in-process: vectorization is delegated to a
remote ML serving layer over HTTP (the `model_server` contract). This keeps the
AI-orchestration service free of torch/transformers/onnx and lets the ML infra
scale, version, and deploy independently.

Wire shape (duck-typed httpx client bound to the server URL)::

    POST {path}  {"texts": ["a", "b"]}  -> {"embeddings": [[...], [...]]}

Accepted response shapes (first match wins): ``{"embeddings": [[...]]}``,
``{"data": [{"embedding": [...]}]}`` (OpenAI-style), or a bare ``[[...]]``.

The parsing/validation is a pure function (``_extract_vectors``) so the contract
is unit-tested offline without llama-index or a live server. The llama-index
``BaseEmbedding`` subclass is a thin wrapper imported lazily behind the [ai]
extra, mirroring the rest of ``app.modules.ai.rag``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.errors import ServiceUnavailableError

if TYPE_CHECKING:
    from llama_index.core.base.embeddings.base import BaseEmbedding


Vector = list[float]


def _extract_vectors(
    data: Any,
    *,
    count: int,
    expected_dim: int | None = None,
) -> list[Vector]:
    """Parse an embedding server reply into ``count`` float vectors.

    Pure: no I/O, no llama-index. Raises ServiceUnavailableError on any shape or
    dimension mismatch so the caller degrades cleanly instead of indexing junk.
    """
    if isinstance(data, dict):
        if "embeddings" in data:
            raw = data["embeddings"]
        elif "data" in data:  # OpenAI-style: [{"embedding": [...]}, ...]
            raw = [item.get("embedding") for item in data["data"]]
        else:
            raise ServiceUnavailableError(
                message="Embedding server reply missing 'embeddings'/'data'",
                code="embedding_server_bad_response",
            )
    elif isinstance(data, list):
        raw = data
    else:
        raise ServiceUnavailableError(
            message=f"Embedding server reply has unexpected type {type(data).__name__}",
            code="embedding_server_bad_response",
        )

    if not isinstance(raw, list) or len(raw) != count:
        raise ServiceUnavailableError(
            message=f"Embedding server returned {_safe_len(raw)} vectors, expected {count}",
            code="embedding_server_bad_response",
        )

    vectors: list[Vector] = []
    for item in raw:
        if not isinstance(item, list) or not item:
            raise ServiceUnavailableError(
                message="Embedding server returned a non-vector element",
                code="embedding_server_bad_response",
            )
        try:
            vector = [float(x) for x in item]
        except (TypeError, ValueError) as exc:
            raise ServiceUnavailableError(
                message="Embedding vector contains non-numeric values",
                code="embedding_server_bad_response",
            ) from exc
        if expected_dim is not None and len(vector) != expected_dim:
            raise ServiceUnavailableError(
                message=f"Embedding dim {len(vector)} != expected {expected_dim}",
                code="embedding_server_dim_mismatch",
            )
        vectors.append(vector)
    return vectors


def _safe_len(value: Any) -> int | str:
    try:
        return len(value)
    except TypeError:
        return "?"


async def aembed_texts(
    client: Any,
    texts: list[str],
    *,
    path: str,
    expected_dim: int | None = None,
) -> list[Vector]:
    """Async: POST texts to the embedding server and return validated vectors."""
    if not texts:
        return []
    data = await _apost(client, path, texts)
    return _extract_vectors(data, count=len(texts), expected_dim=expected_dim)


def embed_texts(
    client: Any,
    texts: list[str],
    *,
    path: str,
    expected_dim: int | None = None,
) -> list[Vector]:
    """Sync variant, for llama-index's synchronous indexing path."""
    if not texts:
        return []
    data = _post(client, path, texts)
    return _extract_vectors(data, count=len(texts), expected_dim=expected_dim)


async def _apost(client: Any, path: str, texts: list[str]) -> Any:
    try:
        response = await client.post(path, json={"texts": texts})
    except Exception as exc:
        raise ServiceUnavailableError(
            message="Embedding server is unreachable",
            code="embedding_server_unavailable",
        ) from exc
    _raise_for_status(response)
    return response.json()


def _post(client: Any, path: str, texts: list[str]) -> Any:
    try:
        response = client.post(path, json={"texts": texts})
    except Exception as exc:
        raise ServiceUnavailableError(
            message="Embedding server is unreachable",
            code="embedding_server_unavailable",
        ) from exc
    _raise_for_status(response)
    return response.json()


def _raise_for_status(response: Any) -> None:
    if response.status_code != 200:
        raise ServiceUnavailableError(
            message=f"Embedding server returned {response.status_code}",
            code="embedding_server_error",
        )


def build_model_server_embedding(
    *,
    base_url: str,
    path: str,
    embed_dim: int,
    timeout: float,
) -> BaseEmbedding:
    """Construct the llama-index embedding backed by a remote ML server.

    Owns its httpx clients (sync + async); the caller (RagAddon) must call
    ``aclose()`` on the returned object at shutdown.
    """
    if not base_url:
        raise RuntimeError(
            "RAG_EMBED_BACKEND=model_server requires RAG_EMBED_SERVER_URL to be set."
        )

    import httpx
    from llama_index.core.base.embeddings.base import BaseEmbedding
    from pydantic import PrivateAttr

    class ModelServerEmbedding(BaseEmbedding):
        """Thin BaseEmbedding delegating vectorization to the remote ML server."""

        _async_client: Any = PrivateAttr()
        _sync_client: Any = PrivateAttr()
        _path: str = PrivateAttr()
        _expected_dim: int = PrivateAttr()

        def __init__(self, **kwargs: Any) -> None:
            super().__init__(model_name="model-server", **kwargs)
            self._async_client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
            self._sync_client = httpx.Client(base_url=base_url, timeout=timeout)
            self._path = path
            self._expected_dim = embed_dim

        async def _aget_text_embeddings(self, texts: list[str]) -> list[Vector]:
            return await aembed_texts(
                self._async_client,
                texts,
                path=self._path,
                expected_dim=self._expected_dim,
            )

        async def _aget_query_embedding(self, query: str) -> Vector:
            return (await self._aget_text_embeddings([query]))[0]

        async def _aget_text_embedding(self, text: str) -> Vector:
            return (await self._aget_text_embeddings([text]))[0]

        def _get_text_embeddings(self, texts: list[str]) -> list[Vector]:
            return embed_texts(
                self._sync_client,
                texts,
                path=self._path,
                expected_dim=self._expected_dim,
            )

        def _get_query_embedding(self, query: str) -> Vector:
            return self._get_text_embeddings([query])[0]

        def _get_text_embedding(self, text: str) -> Vector:
            return self._get_text_embeddings([text])[0]

        async def aclose(self) -> None:
            await self._async_client.aclose()
            self._sync_client.close()

    return ModelServerEmbedding()
