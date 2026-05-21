from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.idempotency.models import IdempotencyKey


@dataclass(frozen=True, slots=True)
class IdempotencyCachedResponse:
    status_code: int
    body: dict[str, Any]


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


async def check_or_store_idempotency_key(
    db: AsyncSession,
    *,
    key: str,
    principal_id: str,
    request_hash: str,
    expires_at: datetime,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> IdempotencyCachedResponse | None:
    record = await _find_record(db, key=key, principal_id=principal_id)
    if record is None:
        db.add(
            IdempotencyKey(
                key=key,
                principal_id=principal_id,
                request_hash=request_hash,
                status="in_progress",
                expires_at=expires_at,
            )
        )
        await db.flush()
        return None

    if record.expires_at <= now():
        _reset_expired_record(
            record,
            request_hash=request_hash,
            expires_at=expires_at,
        )
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
