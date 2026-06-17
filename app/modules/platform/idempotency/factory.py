from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.idempotency.store import IdempotencyStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def build_idempotency_store(
    settings: Settings,
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> IdempotencyStore:
    if settings.IDEMPOTENCY_BACKEND == "postgres":
        if sessionmaker is None:
            raise RuntimeError(
                "sessionmaker is required for postgres idempotency store"
            )
        from app.modules.platform.idempotency.adapters import (
            build_postgres_idempotency_store,
        )

        return build_postgres_idempotency_store(settings, sessionmaker=sessionmaker)

    raise ValueError(f"Unknown IDEMPOTENCY_BACKEND={settings.IDEMPOTENCY_BACKEND!r}")


class IdempotencyAddon:
    name = "idempotency"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.IDEMPOTENCY_ENABLED

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        if settings.IDEMPOTENCY_BACKEND == "postgres" and not settings.DATABASE_ENABLED:
            raise RuntimeError(
                "IdempotencyAddon with IDEMPOTENCY_BACKEND=postgres requires DATABASE_ENABLED"
            )
        resources.idempotency_store = build_idempotency_store(
            settings,
            sessionmaker=resources.sessionmaker,
        )

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        if resources.idempotency_store is not None:
            await resources.idempotency_store.close()
            resources.idempotency_store = None
