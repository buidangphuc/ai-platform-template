"""Lifecycle addon for idempotency; bootstrap owns open/close."""

from __future__ import annotations

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.idempotency.factory import build_idempotency_store


class IdempotencyAddon:
    name = "idempotency"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.IDEMPOTENCY_ENABLED

    async def open(
        self,
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

    async def close(self, resources: ApplicationResources) -> None:
        if resources.idempotency_store is not None:
            await resources.idempotency_store.close()
            resources.idempotency_store = None
