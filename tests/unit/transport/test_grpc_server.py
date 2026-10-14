"""End-to-end gRPC: real in-process server + client through the interceptors.

Covers Search (RAG mapping), Chat (streaming), and auth/scope enforcement.
Uses a fake RAG service and the mock chat streamer — no ML, no network.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import grpc
import pytest

from app.transport.grpc._pb.platform.chat.v1 import chat_pb2, chat_pb2_grpc
from app.transport.grpc._pb.platform.search.v1 import search_pb2, search_pb2_grpc
from app.transport.grpc.chat_stream import build_chat_streamer
from app.transport.grpc.server import build_grpc_server
from tests.factories import build_test_settings

_AUTH = (("authorization", "bearer secret"),)


class _FakeRag:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    async def search(self, query: str, *, top_k=None, filters=None):
        self.calls.append((query, top_k, filters))
        return [
            SimpleNamespace(
                node=SimpleNamespace(metadata={"document_id": "listing-1"}),
                score=0.91,
            )
        ]


def _settings(**overrides):
    base = {
        "AUTH_BEARER_TOKEN": "secret",
        "AUTH_ROLES": "search:read,chat:read",
        "GRPC_REFLECTION_ENABLED": False,
        "CHAT_BACKEND": "mock",
    }
    base.update(overrides)
    return build_test_settings(**base)


async def _start(settings, *, rag=None):
    server = build_grpc_server(
        settings=settings,
        rag_provider=lambda: rag,
        chat_streamer=build_chat_streamer(settings),
    )
    port = server.add_insecure_port("localhost:0")
    await server.start()
    return server, port


async def test_search_maps_rag_hits():
    rag = _FakeRag()
    server, port = await _start(_settings(), rag=rag)
    try:
        async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
            stub = search_pb2_grpc.SearchServiceStub(channel)
            resp = await stub.SearchListings(
                search_pb2.SearchListingsRequest(query="nha pho quan 1"),
                metadata=_AUTH,
            )
        assert [h.listing_id for h in resp.hits] == ["listing-1"]
        assert resp.hits[0].score == pytest.approx(0.91)
        assert rag.calls[0][0] == "nha pho quan 1"
    finally:
        await server.stop(None)


async def test_search_unavailable_when_rag_disabled():
    server, port = await _start(_settings(), rag=None)
    try:
        async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
            stub = search_pb2_grpc.SearchServiceStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as exc:
                await stub.SearchListings(
                    search_pb2.SearchListingsRequest(query="x"), metadata=_AUTH
                )
        assert exc.value.code() == grpc.StatusCode.UNAVAILABLE
    finally:
        await server.stop(None)


async def test_missing_token_is_unauthenticated():
    server, port = await _start(_settings(), rag=_FakeRag())
    try:
        async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
            stub = search_pb2_grpc.SearchServiceStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as exc:
                await stub.SearchListings(search_pb2.SearchListingsRequest(query="x"))
        assert exc.value.code() == grpc.StatusCode.UNAUTHENTICATED
    finally:
        await server.stop(None)


async def test_scope_enforced():
    # principal has only chat:read, not search:read
    server, port = await _start(_settings(AUTH_ROLES="chat:read"), rag=_FakeRag())
    try:
        async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
            stub = search_pb2_grpc.SearchServiceStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as exc:
                await stub.SearchListings(
                    search_pb2.SearchListingsRequest(query="x"), metadata=_AUTH
                )
        assert exc.value.code() == grpc.StatusCode.PERMISSION_DENIED
        assert "insufficient_scope" in exc.value.details()
    finally:
        await server.stop(None)


async def test_chat_streams_tokens_then_done():
    server, port = await _start(_settings(), rag=_FakeRag())
    try:
        async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
            stub = chat_pb2_grpc.ChatServiceStub(channel)
            chunks = [
                chunk
                async for chunk in stub.StreamChat(
                    chat_pb2.StreamChatRequest(session_id="s1", message="hello world"),
                    metadata=_AUTH,
                )
            ]
        assert chunks[-1].done is True
        streamed = "".join(c.delta for c in chunks)
        assert "hello" in streamed and "world" in streamed
    finally:
        await server.stop(None)
