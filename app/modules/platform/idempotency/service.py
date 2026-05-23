from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.platform.idempotency.models import IdempotencyKey
from app.modules.platform.idempotency.store import IdempotencyCachedResponse


def build_request_hash(
    *,
    method: str,
    path: str,
    body: bytes,
    principal_id: str,
) -> str:
    hasher = sha256()
    for value in (method.upper(), path, principal_id):
        hasher.update(value.encode("utf-8"))
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
) -> IdempotencyCachedResponse | None:
    """Race-safe upsert: try ON CONFLICT DO NOTHING first.

    Returns:
        - ``None`` when we won the insert (record is fresh, status="in_progress").
        - ``IdempotencyCachedResponse`` when a completed response was already
          cached for this key.

    Raises ``AppError`` when the key conflicts with a different request or is
    still in progress (within the in-progress timeout window).
    """
    inserted = await _try_insert(
        db,
        key=key,
        principal_id=principal_id,
        request_hash=request_hash,
        expires_at=expires_at,
    )
    if inserted:
        return None

    record = await _find_record(db, key=key, principal_id=principal_id)
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
        _reset_expired_record(record, request_hash=request_hash, expires_at=expires_at)
        await db.flush()
        return None

    if record.request_hash != request_hash:
        raise AppError(
            code="idempotency_key_conflict",
            message="Idempotency-Key was already used for a different request",
            status_code=409,
        )

    if record.status == "completed" and record.response_body is not None:
        return IdempotencyCachedResponse(
            status_code=record.response_status_code or 200,
            body=dict(record.response_body),
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
    status_code: int,
    response_body: Mapping[str, Any],
) -> None:
    record = await _find_record(db, key=key, principal_id=principal_id)
    if record is None:
        raise ValueError("Idempotency record does not exist")

    record.status = "completed"
    record.response_status_code = status_code
    record.response_body = dict(response_body)
    await db.flush()


async def delete_expired_idempotency_keys(
    db: AsyncSession,
    *,
    before: datetime,
) -> int:
    """Remove records whose ``expires_at`` is before ``before``. Returns deleted count."""
    statement = delete(IdempotencyKey).where(IdempotencyKey.expires_at < before)
    result = await db.execute(statement)
    await db.flush()
    return result.rowcount or 0


async def _try_insert(
    db: AsyncSession,
    *,
    key: str,
    principal_id: str,
    request_hash: str,
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
) -> IdempotencyKey | None:
    statement = select(IdempotencyKey).where(
        IdempotencyKey.key == key,
        IdempotencyKey.principal_id == principal_id,
    )
    return await db.scalar(statement)


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
    expires_at: datetime,
) -> None:
    record.request_hash = request_hash
    record.status = "in_progress"
    record.response_status_code = None
    record.response_body = None
    record.expires_at = expires_at
