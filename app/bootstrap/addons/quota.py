"""Lifecycle addon for quota; bootstrap owns open/close."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.quota.factory import (
    build_memory_quota_store,
    build_mongo_quota_store,
    build_postgres_quota_store,
    build_quota_service,
)
from app.modules.platform.quota.service import QuotaService
from app.modules.platform.quota.store import QuotaStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.platform.mongo.gateway import MongoGateway


class QuotaAddon:
    name = "quota"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.QUOTA_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        store: QuotaStore
        backend = settings.QUOTA_BACKEND
        if backend == "memory":
            store = build_memory_quota_store()
        elif backend == "postgres":
            store = build_postgres_quota_store(_sessionmaker(resources))
        elif backend == "mongo":
            mongo_store = build_mongo_quota_store(_mongo(resources))
            await mongo_store.ensure_indexes()
            store = mongo_store
        else:
            raise ValueError(f"Unknown QUOTA_BACKEND={backend!r}")
        resources.quota = build_quota_service(store)

    async def close(self, resources: ApplicationResources) -> None:
        await _quota(resources).close()


def _sessionmaker(
    resources: ApplicationResources,
) -> async_sessionmaker[AsyncSession]:
    if resources.sessionmaker is None:
        raise RuntimeError("QuotaAddon needs an open database sessionmaker")
    return resources.sessionmaker


def _mongo(resources: ApplicationResources) -> MongoGateway:
    if resources.mongo is None:
        raise RuntimeError("QuotaAddon needs an open Mongo gateway")
    return resources.mongo


def _quota(resources: ApplicationResources) -> QuotaService:
    if resources.quota is None:
        raise RuntimeError("QuotaAddon has no open service")
    return resources.quota
