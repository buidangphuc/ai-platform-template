from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.platform.idempotency.store import IdempotencyStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def build_idempotency_store(
    settings: Settings,
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> IdempotencyStore:
    if settings.IDEMPOTENCY_BACKEND == "postgres":
        from app.modules.platform.idempotency.adapters import (
            build_postgres_idempotency_store,
        )

        return build_postgres_idempotency_store(settings, sessionmaker=sessionmaker)

    raise ValueError(f"Unknown IDEMPOTENCY_BACKEND={settings.IDEMPOTENCY_BACKEND!r}")
