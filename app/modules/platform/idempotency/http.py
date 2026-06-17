"""HTTP integration helpers for **synchronous** endpoints only.

Do not use these helpers from async task endpoints (``POST /tasks`` style).
See module docstring in ``__init__.py`` for the conflict rationale and the
recommended async pattern.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.bootstrap.state import get_app_resources, get_app_settings, require
from app.core.errors import AppError
from app.modules.platform.idempotency.service import (
    build_request_hash,
    compute_idempotency_expires_at,
)
from app.modules.platform.idempotency.store import IdempotencyStore

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"

__all__ = [
    "IDEMPOTENCY_KEY_HEADER",
    "IdempotencyRequestState",
    "compute_idempotency_expires_at",
    "get_idempotency_key",
    "replay_or_start_idempotent_request",
    "store_idempotent_response",
]


@dataclass(frozen=True, slots=True)
class IdempotencyRequestState:
    key: str
    principal_id: str
    request_hash: str


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
) -> JSONResponse | None:
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
    cached = await store.check_or_store(
        key=idempotency_key,
        principal_id=principal_id,
        request_hash=request_hash,
        expires_at=expires_at,
    )
    request.state.idempotency_request = IdempotencyRequestState(
        key=idempotency_key,
        principal_id=principal_id,
        request_hash=request_hash,
    )
    if cached is None:
        return None
    return JSONResponse(status_code=cached.status_code, content=cached.body)


async def store_idempotent_response(
    request: Request,
    *,
    status_code: int,
    response_body: Mapping[str, Any],
) -> None:
    state = getattr(request.state, "idempotency_request", None)
    if state is None:
        return
    store = _require_enabled_store(request)
    await store.store_response(
        key=state.key,
        principal_id=state.principal_id,
        status_code=status_code,
        response_body=response_body,
    )


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
