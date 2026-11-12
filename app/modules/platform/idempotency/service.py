from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.platform.idempotency.models import IdempotencyKey
from app.modules.platform.idempotency.store import (
    IdempotencyCachedResponse,
    IdempotencyClaim,
)


def build_request_hash(
    *,
    method: str,
    path: str,
    body: bytes,
    principal_id: str,
    query_string: str = "",
) -> str:
    hasher = sha256()
    for value in (method.upper(), path, principal_id):
        hasher.update(value.encode("utf-8"))
        hasher.update(b"\0")
    if query_string:
        hasher.update(query_string.encode("utf-8"))
        hasher.update(b"\0")
    hasher.update(body)
    return hasher.hexdigest()


def compute_idempotency_expires_at(
    settings: Settings,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> datetime:
    return now() + timedelta(seconds=settings.IDEMPOTENCY_TTL_SECONDS)


async def check_or_store_idempotency_key(
    db: AsyncSession,
    *,
    key: str,
    principal_id: str,
    request_hash: str,
    expires_at: datetime,
    in_progress_timeout_seconds: int,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> IdempotencyCachedResponse | IdempotencyClaim:
    """Race-safe upsert: try ON CONFLICT DO NOTHING first.

    Returns:
        - ``IdempotencyClaim`` when we won the insert or reclaimed an expired or
          stuck record (status="in_progress", fresh ``claim_token``).
        - ``IdempotencyCachedResponse`` when a completed response was already
          cached for this key.

    Raises ``AppError`` when the key conflicts with a different request or is
    still in progress (within the in-progress timeout window).
    """
    claim_token = str(uuid4())
    inserted = await _try_insert(
        db,
        key=key,
        principal_id=principal_id,
        request_hash=request_hash,
        claim_token=claim_token,
        expires_at=expires_at,
    )
    if inserted:
        return IdempotencyClaim(token=claim_token)

    # Row lock: concurrent retries of an expired/stuck key serialize here, so
    # only the first one reclaims it; the rest re-read the refreshed record.
    record = await _find_record(db, key=key, principal_id=principal_id, for_update=True)
    if record is None:
        raise AppError(
            code="idempotency_internal_error",
            message="Idempotency record vanished after insert conflict",
            status_code=500,
        )

    current_now = now()

    if record.expires_at <= current_now or _is_stuck_in_progress(
        record, now=current_now, timeout_seconds=in_progress_timeout_seconds
    ):
        _reset_expired_record(
            record,
            request_hash=request_hash,
            claim_token=claim_token,
            expires_at=expires_at,
            now=current_now,
        )
        await db.flush()
        return IdempotencyClaim(token=claim_token)

    if record.request_hash != request_hash:
        raise AppError(
            code="idempotency_key_conflict",
            message="Idempotency-Key was already used for a different request",
            status_code=409,
        )

    if record.status == "completed" and record.response_body is not None:
        return IdempotencyCachedResponse(
            status_code=record.response_status_code or 200,
            body=_unwrap_body(record.response_body),
        )

    raise AppError(
        code="idempotency_key_in_progress",
        message="Idempotency-Key is already in progress",
        status_code=409,
    )


async def store_idempotency_response(
    db: AsyncSession,
    *,
    key: str,
    principal_id: str,
    claim_token: str,
    status_code: int,
    response_body: Any,
) -> bool:
    """Complete the record only if it is still the caller's in-progress claim.

    The fence (``claim_token`` and ``status = 'in_progress'``) stops a late
    original request from completing a record that was reclaimed (even for a
    byte-identical request) or already completed. Returns ``False`` when the fence
    rejected the write (the stored response is left untouched).
    """
    statement = (
        update(IdempotencyKey)
        .where(
            IdempotencyKey.key == key,
            IdempotencyKey.principal_id == principal_id,
            IdempotencyKey.claim_token == claim_token,
            IdempotencyKey.status == "in_progress",
        )
        .values(
            status="completed",
            response_status_code=status_code,
            response_body=_wrap_body(response_body),
        )
        .returning(IdempotencyKey.id)
    )
    completed = (await db.execute(statement)).scalar_one_or_none() is not None
    await db.flush()
    return completed


async def release_idempotency_claim(
    db: AsyncSession,
    *,
    key: str,
    principal_id: str,
    claim_token: str,
) -> bool:
    """Delete the record only if it is still the caller's in-progress claim.

    Fenced like ``store_idempotency_response``: a claim another request took
    over (reclaim) or a completed record is left untouched.
    """
    statement = (
        delete(IdempotencyKey)
        .where(
            IdempotencyKey.key == key,
            IdempotencyKey.principal_id == principal_id,
            IdempotencyKey.claim_token == claim_token,
            IdempotencyKey.status == "in_progress",
        )
        .returning(IdempotencyKey.id)
    )
    released = (await db.execute(statement)).scalar_one_or_none() is not None
    await db.flush()
    return released


async def delete_expired_idempotency_keys(
    db: AsyncSession,
    *,
    before: datetime,
    limit: int,
) -> int:
    """Remove up to ``limit`` records expired before ``before``; returns the count."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    expired = (
        select(IdempotencyKey.id).where(IdempotencyKey.expires_at < before).limit(limit)
    )
    statement = delete(IdempotencyKey).where(IdempotencyKey.id.in_(expired))
    result = await db.execute(statement)
    await db.flush()
    return cast(CursorResult[Any], result).rowcount


async def _try_insert(
    db: AsyncSession,
    *,
    key: str,
    principal_id: str,
    request_hash: str,
    claim_token: str,
    expires_at: datetime,
) -> bool:
    """Atomic INSERT ... ON CONFLICT DO NOTHING.

    Returns ``True`` when this call performed the insert (we won the race).
    Returns ``False`` when a conflicting row already existed.
    """
    statement = (
        pg_insert(IdempotencyKey)
        .values(
            key=key,
            principal_id=principal_id,
            request_hash=request_hash,
            status="in_progress",
            claim_token=claim_token,
            expires_at=expires_at,
        )
        .on_conflict_do_nothing(
            index_elements=["principal_id", "key"],
        )
        .returning(IdempotencyKey.id)
    )
    result = await db.execute(statement)
    await db.flush()
    return result.scalar_one_or_none() is not None


async def _find_record(
    db: AsyncSession,
    *,
    key: str,
    principal_id: str,
    for_update: bool = False,
) -> IdempotencyKey | None:
    statement = select(IdempotencyKey).where(
        IdempotencyKey.key == key,
        IdempotencyKey.principal_id == principal_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await db.scalar(statement)


_BODY_MARKER = "__idempotent_body__"


def _wrap_body(body: Any) -> Any:
    if isinstance(body, dict) and _BODY_MARKER not in body:
        return body
    return {_BODY_MARKER: body}


def _unwrap_body(stored: Any) -> Any:
    if isinstance(stored, dict) and set(stored) == {_BODY_MARKER}:
        return stored[_BODY_MARKER]
    return stored


def _is_stuck_in_progress(
    record: IdempotencyKey,
    *,
    now: datetime,
    timeout_seconds: int,
) -> bool:
    if record.status != "in_progress":
        return False
    return (now - record.updated_at).total_seconds() >= timeout_seconds


def _reset_expired_record(
    record: IdempotencyKey,
    *,
    request_hash: str,
    claim_token: str,
    expires_at: datetime,
    now: datetime,
) -> None:
    record.request_hash = request_hash
    record.claim_token = claim_token
    record.status = "in_progress"
    record.response_status_code = None
    record.response_body = None
    record.expires_at = expires_at
    record.updated_at = now
