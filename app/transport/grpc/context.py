"""Per-call gRPC context: the authenticated Principal and scope enforcement.

The auth interceptor resolves a ``Principal`` from request metadata and binds it
here for the duration of the call; servicers read it via ``current_principal`` and
gate RPCs with ``ensure_scopes``.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

import grpc

from app.modules.platform.identity.schemas import Principal

_principal: ContextVar[Principal | None] = ContextVar("grpc_principal", default=None)


def current_principal() -> Principal | None:
    return _principal.get()


def bind_principal(principal: Principal) -> Token[Principal | None]:
    return _principal.set(principal)


def reset_principal(token: Token[Principal | None]) -> None:
    _principal.reset(token)


async def ensure_scopes(context: grpc.aio.ServicerContext, *required: str) -> Principal:
    """Abort PERMISSION_DENIED unless the call's Principal holds every scope."""
    principal = current_principal()
    if principal is None:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "no principal on call")
        raise AssertionError("unreachable")  # abort raises; satisfies type checkers
    missing = sorted(frozenset(required) - set(principal.scopes))
    if missing:
        await context.abort(
            grpc.StatusCode.PERMISSION_DENIED,
            f"insufficient_scope: missing {missing}",
        )
        raise AssertionError("unreachable")
    return principal
