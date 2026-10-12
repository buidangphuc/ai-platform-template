"""Lifecycle addon for objects: opens it and registers its close on the stack."""

from __future__ import annotations

from contextlib import AsyncExitStack

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
        stack: AsyncExitStack,
    ) -> None:
        gateway = build_object_gateway(settings)
        stack.push_async_callback(gateway.close)
        resources.objects = gateway
