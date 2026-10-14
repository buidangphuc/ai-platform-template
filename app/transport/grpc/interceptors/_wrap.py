"""Shared helper to wrap a gRPC handler's behavior with a preamble.

grpc.aio ServerInterceptors receive an ``RpcMethodHandler`` and must return one
of the same shape (unary/stream) preserving the (de)serializers. This rebuilds
the handler so unary-unary and unary-stream methods run ``before`` (a coroutine
that may abort) before the original behavior. Other shapes pass through.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

import grpc

Before = Callable[[grpc.aio.ServicerContext], Awaitable[Any]]


def wrap_handler(
    handler: grpc.RpcMethodHandler,
    before: Before,
) -> grpc.RpcMethodHandler:
    if handler.unary_unary is not None:
        inner = handler.unary_unary

        async def unary_unary(request: Any, context: grpc.aio.ServicerContext) -> Any:
            token = await before(context)
            try:
                return await inner(request, context)
            finally:
                _reset(token)

        return grpc.unary_unary_rpc_method_handler(
            unary_unary,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )

    if handler.unary_stream is not None:
        inner_stream = handler.unary_stream

        async def unary_stream(
            request: Any, context: grpc.aio.ServicerContext
        ) -> AsyncIterator[Any]:
            token = await before(context)
            try:
                stream = cast("AsyncIterator[Any]", inner_stream(request, context))
                async for response in stream:
                    yield response
            finally:
                _reset(token)

        return grpc.unary_stream_rpc_method_handler(
            unary_stream,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )

    # stream-unary / stream-stream: not used by team-ai's contract — pass through.
    return handler


def _reset(token: Any) -> None:
    """Reset a contextvar Token if ``before`` returned one."""
    if token is None:
        return
    var = getattr(token, "var", None)
    if var is not None:
        var.reset(token)
