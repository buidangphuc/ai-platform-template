"""Lifecycle addon for quota; bootstrap owns open/close."""

from __future__ import annotations

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.quota.factory import build_quota_service


class QuotaAddon:
    name = "quota"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.QUOTA_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        if settings.QUOTA_BACKEND == "postgres" and not settings.DATABASE_ENABLED:
            raise RuntimeError(
                "QuotaAddon with QUOTA_BACKEND=postgres requires DATABASE_ENABLED"
            )
        if settings.QUOTA_BACKEND == "mongo" and not settings.MONGO_ENABLED:
            raise RuntimeError(
                "QuotaAddon with QUOTA_BACKEND=mongo requires MONGO_ENABLED"
            )
        resources.quota = build_quota_service(
            settings,
            sessionmaker=resources.sessionmaker,
            mongo=resources.mongo,
        )

    async def close(self, resources: ApplicationResources) -> None:
        if resources.quota is not None:
            await resources.quota.close()
            resources.quota = None
