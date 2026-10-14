"""SearchService gRPC servicer — thin transport over the RAG search machinery.

Parses the request, enforces scope, calls ``KnowledgeRetrievalService.search``,
and maps hits back to the platform contract. Embedding/vectorization happens in
the RAG service via the remote model-server seam — this layer holds no ML.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import grpc

from app.core.errors import ServiceUnavailableError
from app.transport.grpc._pb.platform.common.v1 import common_pb2
from app.transport.grpc._pb.platform.search.v1 import search_pb2, search_pb2_grpc
from app.transport.grpc.context import ensure_scopes

if TYPE_CHECKING:
    from app.modules.ai.rag.service import KnowledgeRetrievalService

RagProvider = Callable[[], "KnowledgeRetrievalService | None"]


class SearchServicer(search_pb2_grpc.SearchServiceServicer):
    def __init__(self, rag_provider: RagProvider) -> None:
        self._rag_provider = rag_provider

    async def SearchListings(
        self,
        request: search_pb2.SearchListingsRequest,
        context: grpc.aio.ServicerContext,
    ) -> search_pb2.SearchListingsResponse:
        await ensure_scopes(context, "search:read")

        rag = self._rag_provider()
        if rag is None:
            await context.abort(
                grpc.StatusCode.UNAVAILABLE, "search is not enabled (RAG_ENABLED=false)"
            )
            raise AssertionError("unreachable")

        top_k = request.page.page_size or None
        filters = cast(
            "dict[str, str | int | float | bool] | None",
            dict(request.filters) or None,
        )
        try:
            nodes = await rag.search(request.query, top_k=top_k, filters=filters)
        except ServiceUnavailableError as exc:
            await context.abort(grpc.StatusCode.UNAVAILABLE, exc.message)
            raise AssertionError("unreachable") from exc

        hits = [
            search_pb2.SearchHit(listing_id=_listing_id(node), score=_score(node))
            for node in nodes
        ]
        return search_pb2.SearchListingsResponse(
            hits=hits,
            page=common_pb2.PageResponse(next_cursor="", total=len(hits)),
        )


def _listing_id(node: Any) -> str:
    inner = getattr(node, "node", node)
    metadata = getattr(inner, "metadata", {}) or {}
    return str(metadata.get("document_id") or getattr(inner, "ref_doc_id", "") or "")


def _score(node: Any) -> float:
    score = getattr(node, "score", None)
    return float(score) if score is not None else 0.0
