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
        match settings.QUOTA_BACKEND:
            case "memory":
                store = build_memory_quota_store()
            case "postgres":
                store = build_postgres_quota_store(
                    opened(resources.sessionmaker, "sessionmaker")
                )
            case "mongo":
                mongo_store = build_mongo_quota_store(opened(resources.mongo, "mongo"))
                await mongo_store.ensure_indexes()
                store = mongo_store
        quota = build_quota_service(store)
        stack.push_async_callback(quota.close)
        resources.quota = quota
