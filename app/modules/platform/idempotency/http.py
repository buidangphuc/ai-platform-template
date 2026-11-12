"""HTTP integration helpers for **synchronous** endpoints only.

Do not use these helpers from async task endpoints (``POST /tasks`` style).
See module docstring in ``__init__.py`` for the conflict rationale and the
recommended async pattern.
"""

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.utils import is_body_allowed_for_status_code
from pydantic import TypeAdapter

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

logger = logging.getLogger(__name__)


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
) -> Response | IdempotentCall | None:
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
        query_string=request.url.query,
    )
    outcome = await store.check_or_store(
        key=idempotency_key,
        principal_id=principal_id,
        request_hash=request_hash,
        expires_at=expires_at,
    )
    match outcome:
        case IdempotencyCachedResponse():
            if not is_body_allowed_for_status_code(outcome.status_code):
                return Response(status_code=outcome.status_code)
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
    response_body: Any,
) -> bool:
    """Cache the response; ``False`` if the claim was reclaimed meanwhile."""
    return await call.store.store_response(
        key=call.key,
        principal_id=call.principal_id,
        claim_token=call.claim_token,
        status_code=status_code,
        response_body=response_body,
    )


async def release_idempotent_call(call: IdempotentCall) -> bool:
    """Drop the claim this request made so the key can be retried."""
    return await call.store.release(
        key=call.key,
        principal_id=call.principal_id,
        claim_token=call.claim_token,
    )


def declared_response(request: Request, result: Any) -> tuple[int, Any]:
    """Status and JSON body FastAPI sends for ``result`` on the matched route.

    Honours ``status_code``, ``response_model`` and the route's
    ``response_model_include/exclude/by_alias/exclude_unset/exclude_defaults/
    exclude_none``. Without a ``response_model`` the body is
    ``jsonable_encoder(result)``.
    """
    route = request.scope.get("route")
    if not isinstance(route, APIRoute):
        return 200, jsonable_encoder(result)
    status_code = route.status_code or 200
    if route.response_model is None:
        return status_code, jsonable_encoder(result)
    adapter = TypeAdapter(route.response_model)
    validated = adapter.validate_python(result, from_attributes=True)
    body = adapter.dump_python(
        validated,
        mode="json",
        include=route.response_model_include,
        exclude=route.response_model_exclude,
        by_alias=route.response_model_by_alias,
        exclude_unset=route.response_model_exclude_unset,
        exclude_defaults=route.response_model_exclude_defaults,
        exclude_none=route.response_model_exclude_none,
    )
    return status_code, body


def idempotent(handler: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Optional route guard: replay a repeated ``Idempotency-Key`` request.

    Opt-in example: no route in this template enables it. Place it under the route
    decorator on a handler that declares ``request: Request`` and returns
    any JSON-serializable value::

        @router.post("/reports")
        @idempotent
        async def create_report(payload: Payload, request: Request) -> dict: ...

    Without the header the handler runs untouched. With it, a completed key
    replays the stored response without running the handler. The stored
    response is what the client received for the first request: the route's
    ``status_code`` (200 when none) and the body after ``response_model``
    filtering (any JSON value, including lists and scalars). The request hash
    covers method, path, query string, body and principal. When the handler
    raises or is cancelled, the claim is released so the next request with the
    same key runs the handler again. A handler that returns a ``Response``
    object is not stored: its claim is released. Requires
    ``IDEMPOTENCY_ENABLED=true``.
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
        if isinstance(outcome, Response):
            return outcome
        if outcome is None:
            return await handler(*args, **kwargs)
        try:
            result = await handler(*args, **kwargs)
            if isinstance(result, Response):
                await _release_quietly(outcome)
                return result
            status_code, response_body = declared_response(request, result)
        except BaseException:
            await _release_quietly(outcome)
            raise
        await store_idempotent_response(
            outcome, status_code=status_code, response_body=response_body
        )
        return result

    return wrapper


async def _release_quietly(call: IdempotentCall) -> None:
    try:
        await asyncio.shield(release_idempotent_call(call))
    except Exception:
        logger.warning("idempotency_release_failed", exc_info=True)


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
