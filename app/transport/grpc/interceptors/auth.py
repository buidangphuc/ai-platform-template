"""Auth interceptor: resolve a Principal from gRPC metadata (bearer today).

Mirrors the HTTP path (``app.modules.platform.identity.auth``) but for gRPC —
reusing the same transport-neutral ``authenticate_bearer_token`` so both surfaces
issue the same Principal. JWT/cookie is a future extension (platform ADR-0003).
"""

from __future__ import annotations

from contextvars import Token
from typing import Any

import grpc

from app.core.config import Settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.modules.platform.identity.auth import authenticate_bearer_token
from app.modules.platform.identity.schemas import Principal
from app.transport.grpc.context import _principal
from app.transport.grpc.interceptors._wrap import wrap_handler


class AuthInterceptor(grpc.aio.ServerInterceptor):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def intercept_service(
        self,
        continuation: Any,
        handler_call_details: Any,
    ) -> Any:
        handler = await continuation(handler_call_details)
        if handler is None:
            return handler

        async def before(context: grpc.aio.ServicerContext) -> Token[Principal | None]:
            principal = await self._authenticate(context)
            return _principal.set(principal)

        return wrap_handler(handler, before)

    async def _authenticate(self, context: grpc.aio.ServicerContext) -> Principal:
        metadata = dict(context.invocation_metadata() or ())
        raw = metadata.get("authorization")
        authorization = raw.decode() if isinstance(raw, bytes) else raw
        try:
            return await authenticate_bearer_token(
                authorization, settings=self._settings
            )
        except UnauthorizedError as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, exc.message)
        except ForbiddenError as exc:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, exc.message)
        raise AssertionError("unreachable")  # abort raises
