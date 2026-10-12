from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.messaging.outbox.store import OutboxStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def build_outbox_store(
    settings: Settings,
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> OutboxStore:
    if settings.OUTBOX_BACKEND == "postgres":
        if sessionmaker is None:
            raise RuntimeError("sessionmaker is required for postgres outbox store")
        from app.modules.messaging.outbox.adapters import PostgresOutboxStore

        return PostgresOutboxStore(sessionmaker)

    raise ValueError(f"Unknown OUTBOX_BACKEND={settings.OUTBOX_BACKEND!r}")
