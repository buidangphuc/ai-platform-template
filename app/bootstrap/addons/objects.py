"""Lifecycle addon for objects; bootstrap owns open/close."""

from __future__ import annotations

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.objects.factory import build_object_gateway


class ObjectAddon:
    name = "objects"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.OBJECTS_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        resources.objects = build_object_gateway(settings)

    async def close(self, resources: ApplicationResources) -> None:
        if resources.objects is not None:
            await resources.objects.close()
            resources.objects = None
