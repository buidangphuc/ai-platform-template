"""Tracing interceptor: bridge the ``x-request-id`` correlation id across the hop.

Reads ``x-request-id`` from incoming metadata (or mints one) and binds it to the
request-context so logs on this call carry it — the same convention as the HTTP
``RequestIdMiddleware``. W3C ``traceparent`` / OpenTelemetry propagation is the
next layer (platform ADR-0004); this keeps the human-facing correlation id.
"""

from __future__ import annotations

import uuid
from contextvars import Token
from typing import Any

import grpc

from app.core.request_context import _request_id
from app.transport.grpc.interceptors._wrap import wrap_handler


class TracingInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(
        self,
        continuation: Any,
        handler_call_details: Any,
    ) -> Any:
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler

        async def before(context: grpc.aio.ServicerContext) -> Token[str]:
            metadata = dict(context.invocation_metadata() or ())
            raw = metadata.get("x-request-id")
            incoming = raw.decode() if isinstance(raw, bytes) else raw
            request_id = incoming or f"req_{uuid.uuid4().hex}"
            return _request_id.set(request_id)

        return wrap_handler(handler, before)
