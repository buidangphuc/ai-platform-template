"""HTTP integration helpers for **synchronous** endpoints only.

Do not use these helpers from async task endpoints (``POST /tasks`` style).
See module docstring in ``__init__.py`` for the conflict rationale and the
recommended async pattern.
"""

import functools
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.bootstrap.state import get_app_resources, get_app_settings, require
from app.core.errors import AppError
from app.modules.platform.idempotency.service import (
    build_request_hash,
    compute_idempotency_expires_at,
)
from app.modules.platform.idempotency.store import (
    IdempotencyCachedResponse,
    IdempotencyClaim,
    IdempotencyStore,
)
from app.modules.platform.identity.auth import require_principal

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"


@dataclass(frozen=True, slots=True)
class IdempotentCall:
    """Handle for a claimed key; pass it to ``store_idempotent_response``."""

    key: str
    principal_id: str
    claim_token: str
    store: IdempotencyStore


def get_idempotency_key(request: Request) -> str | None:
    raw_value = request.headers.get(IDEMPOTENCY_KEY_HEADER)
    if raw_value is None:
        request.state.idempotency_key = None
        return None

    idempotency_key = raw_value.strip()
    if not idempotency_key:
        raise AppError(
            code="invalid_idempotency_key",
            message="Idempotency-Key must not be blank",
            status_code=400,
        )
    max_length = get_app_settings(request.app).IDEMPOTENCY_KEY_MAX_LENGTH
    if len(idempotency_key) > max_length:
        raise AppError(
            code="invalid_idempotency_key",
            message=f"Idempotency-Key is too long (max {max_length} characters)",
            status_code=400,
        )

    request.state.idempotency_key = idempotency_key
    return idempotency_key


async def replay_or_start_idempotent_request(
    request: Request,
    *,
    principal_id: str,
    body: bytes,
    expires_at: datetime,
) -> JSONResponse | IdempotentCall | None:
    """Claim the request's key.

    Returns ``None`` when no ``Idempotency-Key`` header is present, a
    ``JSONResponse`` to return as-is when a completed response is replayed, or
    an ``IdempotentCall`` once the key is claimed (run the handler, then pass
    the call to ``store_idempotent_response``).
    """
    idempotency_key = get_idempotency_key(request)
    if idempotency_key is None:
        return None

    store = _require_enabled_store(request)
    request_hash = build_request_hash(
        method=request.method,
        path=request.url.path,
        body=body,
        principal_id=principal_id,
    )
    outcome = await store.check_or_store(
        key=idempotency_key,
        principal_id=principal_id,
        request_hash=request_hash,
        expires_at=expires_at,
    )
    match outcome:
        case IdempotencyCachedResponse():
            return JSONResponse(status_code=outcome.status_code, content=outcome.body)
        case IdempotencyClaim():
            return IdempotentCall(
                key=idempotency_key,
                principal_id=principal_id,
                claim_token=outcome.token,
                store=store,
            )


async def store_idempotent_response(
    call: IdempotentCall,
    *,
    status_code: int,
    response_body: Mapping[str, Any],
) -> bool:
    """Cache the response; ``False`` if the claim was reclaimed meanwhile."""
    return await call.store.store_response(
        key=call.key,
        principal_id=call.principal_id,
        claim_token=call.claim_token,
        status_code=status_code,
        response_body=response_body,
    )


def idempotent(handler: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Optional route guard: replay a repeated ``Idempotency-Key`` request.

    Opt-in example: no route in this template enables it. Place it under the route
    decorator on a handler that declares ``request: Request`` and returns
    a dict or Pydantic model (stored and replayed with status 200)::

        @router.post("/reports")
        @idempotent
        async def create_report(payload: Payload, request: Request) -> dict: ...

    Without the header the handler runs untouched. With it, a completed key
    replays the stored response without running the handler, and the first
    successful result is stored. Requires ``IDEMPOTENCY_ENABLED=true``.
    """

    @functools.wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        request = next(
            value for value in (*args, *kwargs.values()) if isinstance(value, Request)
        )
        principal = getattr(
            request.state, "principal", None
        ) or await require_principal(request)
        outcome = await replay_or_start_idempotent_request(
            request,
            principal_id=principal.id,
            body=await request.body(),
            expires_at=compute_idempotency_expires_at(get_app_settings(request.app)),
        )
        if isinstance(outcome, JSONResponse):
            return outcome
        result = await handler(*args, **kwargs)
        if outcome is not None:
            await store_idempotent_response(
                outcome, status_code=200, response_body=jsonable_encoder(result)
            )
        return result

    return wrapper


def _require_enabled_store(request: Request) -> IdempotencyStore:
    settings = get_app_settings(request.app)
    if not settings.IDEMPOTENCY_ENABLED:
        raise AppError(
            code="idempotency_disabled",
            message="Idempotency is disabled",
            status_code=503,
        )
    return require(
        get_app_resources(request.app).idempotency_store,
        code="idempotency_unavailable",
        message="Idempotency store is unavailable",
    )
