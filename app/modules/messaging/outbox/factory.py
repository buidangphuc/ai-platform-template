from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
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


class OutboxAddon:
    name = "outbox"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.OUTBOX_ENABLED

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        if settings.OUTBOX_BACKEND == "postgres" and not settings.DATABASE_ENABLED:
            raise RuntimeError(
                "OutboxAddon with OUTBOX_BACKEND=postgres requires DATABASE_ENABLED"
            )
        resources.outbox_store = build_outbox_store(
            settings,
            sessionmaker=resources.sessionmaker,
        )

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        if resources.outbox_store is not None:
            await resources.outbox_store.close()
            resources.outbox_store = None
