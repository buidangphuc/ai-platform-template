"""Lifecycle addon for OpenTelemetry: builds the providers, flushes them on close."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.telemetry import require_otel


class TelemetryAddon:
    name = "telemetry"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.OTEL_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        require_otel()
        from app.core.telemetry_otel import build_telemetry, install_globals

        telemetry = build_telemetry(settings)
        install_globals(telemetry)
        # Shutdown flushes pending batches over the network: keep it off the loop.
        stack.push_async_callback(asyncio.to_thread, telemetry.shutdown)
        resources.telemetry = telemetry
