from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.modules.platform.idempotency.service import (
    check_or_store_idempotency_key,
    delete_expired_idempotency_keys,
    store_idempotency_response,
)
from app.modules.platform.idempotency.store import IdempotencyCachedResponse


class PostgresIdempotencyStore:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        in_progress_timeout_seconds: int,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.in_progress_timeout_seconds = in_progress_timeout_seconds

    async def check_or_store(
        self,
        *,
        key: str,
        principal_id: str,
        request_hash: str,
        expires_at: datetime,
    ) -> IdempotencyCachedResponse | None:
        async with self.sessionmaker() as session, session.begin():
            return await check_or_store_idempotency_key(
                session,
                key=key,
                principal_id=principal_id,
                request_hash=request_hash,
                expires_at=expires_at,
                in_progress_timeout_seconds=self.in_progress_timeout_seconds,
            )

    async def store_response(
        self,
        *,
        key: str,
        principal_id: str,
        status_code: int,
        response_body: Mapping[str, Any],
    ) -> None:
        async with self.sessionmaker() as session, session.begin():
            await store_idempotency_response(
                session,
                key=key,
                principal_id=principal_id,
                status_code=status_code,
                response_body=response_body,
            )

    async def delete_expired(self, *, before: datetime) -> int:
        async with self.sessionmaker() as session, session.begin():
            return await delete_expired_idempotency_keys(session, before=before)

    async def close(self) -> None:
        return None


def build_postgres_idempotency_store(
    settings: Settings,
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> PostgresIdempotencyStore:
    return PostgresIdempotencyStore(
        sessionmaker,
        in_progress_timeout_seconds=settings.IDEMPOTENCY_IN_PROGRESS_TIMEOUT_SECONDS,
    )
