"""Lifecycle addon for idempotency; bootstrap owns open/close."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.idempotency.factory import build_idempotency_store
from app.modules.platform.idempotency.store import IdempotencyStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class IdempotencyAddon:
    name = "idempotency"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.IDEMPOTENCY_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        resources.idempotency_store = build_idempotency_store(
            settings,
            sessionmaker=_sessionmaker(resources),
        )

    async def close(self, resources: ApplicationResources) -> None:
        await _store(resources).close()


def _sessionmaker(
    resources: ApplicationResources,
) -> async_sessionmaker[AsyncSession]:
    if resources.sessionmaker is None:
        raise RuntimeError("IdempotencyAddon needs an open database sessionmaker")
    return resources.sessionmaker


def _store(resources: ApplicationResources) -> IdempotencyStore:
    if resources.idempotency_store is None:
        raise RuntimeError("IdempotencyAddon has no open store")
    return resources.idempotency_store
