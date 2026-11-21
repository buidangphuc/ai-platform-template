from __future__ import annotations

import httpx
import pytest

from app.core.errors import ServiceUnavailableError
from app.core.request_context import reset_request_id, set_request_id
from app.modules.ai.rag.embeddings import (
    build_model_server_embedding,
    parse_embedding_reply,
)
from app.modules.platform.http.upstream import UpstreamClient
from tests.http_server import LocalHttpServer, Reply

PATH = "/embed"
DIM = 3


def _code(exc_info: pytest.ExceptionInfo[ServiceUnavailableError]) -> str:
    return exc_info.value.code


def test_parser_accepts_the_embeddings_shape():
    reply = {"embeddings": [[1, 2, 3], [4.5, 5, 6]]}

    assert parse_embedding_reply(reply, count=2, dim=DIM) == [
        [1.0, 2.0, 3.0],
        [4.5, 5.0, 6.0],
    ]


def test_parser_accepts_the_openai_data_shape():
    reply = {"data": [{"embedding": [1, 2, 3]}, {"embedding": [4, 5, 6]}]}

    assert parse_embedding_reply(reply, count=2, dim=DIM) == [
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
    ]


def test_parser_accepts_a_bare_list():
    assert parse_embedding_reply([[1, 2, 3]], count=1, dim=DIM) == [[1.0, 2.0, 3.0]]


def test_parser_prefers_embeddings_over_data():
    reply = {"embeddings": [[1, 1, 1]], "data": [{"embedding": [2, 2, 2]}]}

    assert parse_embedding_reply(reply, count=1, dim=DIM) == [[1.0, 1.0, 1.0]]


@pytest.mark.parametrize(
    "reply",
    [
        {"embeddings": [[1, 2, 3]]},
        {"embeddings": [[1, 2, 3], [1, 2, 3], [1, 2, 3]]},
        {"data": [{"embedding": [1, 2, 3]}]},
        [[1, 2, 3]],
    ],
)
def test_parser_rejects_a_wrong_vector_count(reply):
    with pytest.raises(ServiceUnavailableError) as exc:
        parse_embedding_reply(reply, count=2, dim=DIM)

    assert _code(exc) == "embedding_server_bad_response"


@pytest.mark.parametrize(
    "reply",
    [
        {"embeddings": [[]]},
        {"embeddings": [None]},
        {"embeddings": ["abc"]},
        {"data": [{"embedding": []}]},
        {"data": [{}]},
        {"data": [None]},
    ],
)
def test_parser_rejects_an_empty_or_missing_vector(reply):
    with pytest.raises(ServiceUnavailableError) as exc:
        parse_embedding_reply(reply, count=1, dim=DIM)

    assert _code(exc) == "embedding_server_bad_response"


@pytest.mark.parametrize(
    "vector",
    [
        [1, "x", 3],
        [1, None, 3],
        [1, True, 3],
        [1, [2], 3],
        [1, "2", 3],
        [1, float("nan"), 3],
        [1, float("inf"), 3],
    ],
)
def test_parser_rejects_non_numeric_values(vector):
    with pytest.raises(ServiceUnavailableError) as exc:
        parse_embedding_reply({"embeddings": [vector]}, count=1, dim=DIM)

    assert _code(exc) == "embedding_server_bad_response"


@pytest.mark.parametrize("vector", [[1, 2], [1, 2, 3, 4]])
def test_parser_rejects_a_wrong_dimension(vector):
    with pytest.raises(ServiceUnavailableError) as exc:
        parse_embedding_reply({"embeddings": [vector]}, count=1, dim=DIM)

    assert _code(exc) == "embedding_server_dim_mismatch"


@pytest.mark.parametrize(
    "reply",
    ["text", 7, None, {}, {"vectors": [[1, 2, 3]]}, {"embeddings": "abc"}, {"data": 1}],
)
def test_parser_rejects_an_unrecognised_reply(reply):
    with pytest.raises(ServiceUnavailableError) as exc:
        parse_embedding_reply(reply, count=1, dim=DIM)

    assert _code(exc) == "embedding_server_bad_response"


@pytest.fixture()
async def embedding(local_http_server: LocalHttpServer):
    client = UpstreamClient(
        "rag_embeddings", httpx.AsyncClient(base_url=local_http_server.url, timeout=2.0)
    )
    yield build_model_server_embedding(client, path=PATH, dim=DIM)
    await client.aclose()


async def test_texts_are_posted_to_the_configured_path(local_http_server, embedding):
    local_http_server.script(PATH, Reply(json={"embeddings": [[1, 0, 0], [0, 1, 0]]}))

    vectors = await embedding.aget_text_embedding_batch(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    [request] = local_http_server.requests
    assert request.method == "POST"
    assert request.path == PATH
    assert request.json() == {"texts": ["first", "second"]}


async def test_a_query_is_embedded_as_a_single_text(local_http_server, embedding):
    local_http_server.script(PATH, Reply(json={"embeddings": [[0, 0, 1]]}))

    vector = await embedding.aget_query_embedding("what is it")

    assert vector == [0.0, 0.0, 1.0]
    assert local_http_server.requests[0].json() == {"texts": ["what is it"]}


async def test_a_non_200_reply_is_embedding_server_error(local_http_server, embedding):
    local_http_server.script(PATH, Reply(status=500))

    with pytest.raises(ServiceUnavailableError) as exc:
        await embedding.aget_query_embedding("x")

    assert _code(exc) == "embedding_server_error"


async def test_a_stopped_server_is_embedding_server_unavailable(
    local_http_server, embedding
):
    await local_http_server.stop()

    with pytest.raises(ServiceUnavailableError) as exc:
        await embedding.aget_query_embedding("x")

    assert _code(exc) == "embedding_server_unavailable"


async def test_a_wrong_sized_reply_is_never_returned(local_http_server, embedding):
    local_http_server.script(PATH, Reply(json={"embeddings": [[1, 2]]}))

    with pytest.raises(ServiceUnavailableError) as exc:
        await embedding.aget_query_embedding("x")

    assert _code(exc) == "embedding_server_dim_mismatch"


async def test_the_current_request_id_reaches_the_server(local_http_server, embedding):
    local_http_server.script(PATH, Reply(json={"embeddings": [[1, 0, 0]]}))

    token = set_request_id("req_embed")
    try:
        await embedding.aget_query_embedding("x")
    finally:
        reset_request_id(token)

    assert local_http_server.requests[0].headers["x-request-id"] == "req_embed"


def test_sync_methods_point_to_the_async_ones(embedding):
    with pytest.raises(RuntimeError, match="aget_query_embedding"):
        embedding.get_query_embedding("x")
    with pytest.raises(RuntimeError, match="aget_text_embedding"):
        embedding.get_text_embedding("x")
    with pytest.raises(RuntimeError, match="aget_text_embedding_batch"):
        embedding.get_text_embedding_batch(["x"])
