from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.bootstrap.state import attach_app_resource, optional_app_resource
from app.core.config import Settings
from app.modules.idempotency.store import IdempotencyStore

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
        from app.modules.idempotency.adapters import PostgresIdempotencyStore

        return PostgresIdempotencyStore(sessionmaker)

    raise ValueError(f"Unknown IDEMPOTENCY_BACKEND={settings.IDEMPOTENCY_BACKEND!r}")


class IdempotencyAddon:
    name = "idempotency"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.IDEMPOTENCY_ENABLED

    def required_resources(self, settings: Settings) -> tuple[str, ...]:
        return ("database",) if settings.IDEMPOTENCY_BACKEND == "postgres" else ()

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        attach_app_resource(
            app,
            resources,
            "idempotency_store",
            build_idempotency_store(
                settings,
                sessionmaker=resources.sessionmaker,
            ),
        )

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        store = optional_app_resource(app, "idempotency_store")
        if store is not None:
            await store.close()
