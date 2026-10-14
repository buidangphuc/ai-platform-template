"""Assemble and serve the team-ai gRPC server (platform-core contract).

Registers SearchService + ChatService behind the tracing and auth interceptors,
plus the standard health and (optional) reflection services. ``build_grpc_server``
returns a ready-but-unstarted server so tests can drive it in-process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from loguru import logger

from app.core.config import Settings
from app.transport.grpc._pb.platform.chat.v1 import chat_pb2, chat_pb2_grpc
from app.transport.grpc._pb.platform.search.v1 import search_pb2, search_pb2_grpc
from app.transport.grpc.chat_stream import ChatStreamer
from app.transport.grpc.interceptors.auth import AuthInterceptor
from app.transport.grpc.interceptors.tracing import TracingInterceptor
from app.transport.grpc.servicers.chat import ChatServicer
from app.transport.grpc.servicers.search import SearchServicer

if TYPE_CHECKING:
    from app.transport.grpc.servicers.search import RagProvider


def build_grpc_server(
    *,
    settings: Settings,
    rag_provider: RagProvider,
    chat_streamer: ChatStreamer,
) -> grpc.aio.Server:
    server = grpc.aio.server(
        interceptors=(TracingInterceptor(), AuthInterceptor(settings))
    )

    search_pb2_grpc.add_SearchServiceServicer_to_server(
        SearchServicer(rag_provider), server
    )
    chat_pb2_grpc.add_ChatServiceServicer_to_server(ChatServicer(chat_streamer), server)

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    for service in _service_names():
        health_servicer.set(service, health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    if settings.GRPC_REFLECTION_ENABLED:
        from grpc_reflection.v1alpha import reflection

        reflection.enable_server_reflection(
            (*_service_names(), reflection.SERVICE_NAME), server
        )

    return server


def _service_names() -> tuple[str, ...]:
    return (
        search_pb2.DESCRIPTOR.services_by_name["SearchService"].full_name,
        chat_pb2.DESCRIPTOR.services_by_name["ChatService"].full_name,
        health_pb2.DESCRIPTOR.services_by_name["Health"].full_name,
    )


async def serve(
    *,
    settings: Settings,
    rag_provider: RagProvider,
    chat_streamer: ChatStreamer,
) -> None:
    server = build_grpc_server(
        settings=settings, rag_provider=rag_provider, chat_streamer=chat_streamer
    )
    bind = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
    server.add_insecure_port(bind)
    await server.start()
    logger.info(
        "grpc.server.started bind={} reflection={}",
        bind,
        settings.GRPC_REFLECTION_ENABLED,
    )
    try:
        await server.wait_for_termination()
    finally:
        await server.stop(settings.GRPC_GRACE_SECONDS)
        logger.info("grpc.server.stopped")
