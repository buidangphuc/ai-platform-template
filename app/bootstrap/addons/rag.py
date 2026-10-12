"""Lifecycle addon for rag: opens it and registers its close on the stack."""

from __future__ import annotations

from contextlib import AsyncExitStack

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
        stack: AsyncExitStack,
    ) -> None:
        # The retrieval service holds no connection; nothing to register.
        resources.rag_service = build_rag_service(settings)
