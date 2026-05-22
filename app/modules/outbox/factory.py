from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.bootstrap.state import attach_app_resource, optional_app_resource
from app.core.config import Settings
from app.modules.outbox.store import OutboxStore

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
        from app.modules.outbox.adapters import PostgresOutboxStore

        return PostgresOutboxStore(sessionmaker)

    raise ValueError(f"Unknown OUTBOX_BACKEND={settings.OUTBOX_BACKEND!r}")


class OutboxAddon:
    name = "outbox"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.OUTBOX_ENABLED

    def required_resources(self, settings: Settings) -> tuple[str, ...]:
        return ("database",) if settings.OUTBOX_BACKEND == "postgres" else ()

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        attach_app_resource(
            app,
            resources,
            "outbox_store",
            build_outbox_store(
                settings,
                sessionmaker=resources.sessionmaker,
            ),
        )

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        store = optional_app_resource(app, "outbox_store")
        if store is not None:
            await store.close()
