"""Lifecycle addon for rag; bootstrap owns open/close."""

from __future__ import annotations

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.ai.rag.factory import build_rag_service


class RagAddon:
    name = "rag"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.RAG_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        resources.rag_service = build_rag_service(settings)

    async def close(self, resources: ApplicationResources) -> None:
        """Nothing to release: the retrieval service holds no connection."""
