"""Lifecycle addon for quota: opens it and registers its close on the stack."""

from __future__ import annotations

from contextlib import AsyncExitStack

from app.bootstrap.resources import ApplicationResources, opened
from app.core.config import Settings
from app.modules.platform.quota.factory import (
    build_memory_quota_store,
    build_mongo_quota_store,
    build_postgres_quota_store,
    build_quota_service,
)
from app.modules.platform.quota.store import QuotaStore


class QuotaAddon:
    name = "quota"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.QUOTA_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        store: QuotaStore
        backend = settings.QUOTA_BACKEND
        if backend == "memory":
            store = build_memory_quota_store()
        elif backend == "postgres":
            store = build_postgres_quota_store(
                opened(resources.sessionmaker, "sessionmaker")
            )
        elif backend == "mongo":
            mongo_store = build_mongo_quota_store(opened(resources.mongo, "mongo"))
            await mongo_store.ensure_indexes()
            store = mongo_store
        else:
            raise ValueError(f"Unknown QUOTA_BACKEND={backend!r}")
        quota = build_quota_service(store)
        stack.push_async_callback(quota.close)
        resources.quota = quota
