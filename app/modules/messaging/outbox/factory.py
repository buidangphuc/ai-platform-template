from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.messaging.outbox.store import OutboxStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def build_outbox_store(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> OutboxStore:
    match settings.OUTBOX_BACKEND:
        case "postgres":
            from app.modules.messaging.outbox.adapters import PostgresOutboxStore

            return PostgresOutboxStore(sessionmaker)
        case backend:
            raise ValueError(f"Unknown OUTBOX_BACKEND={backend!r}")
