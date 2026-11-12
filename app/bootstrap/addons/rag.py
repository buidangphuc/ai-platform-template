"""Lifecycle addon for rag: opens it and registers its close on the stack."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.ai.rag.embeddings import SupportsAclose
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
        service = await asyncio.to_thread(build_rag_service, settings)
        stack.push_async_callback(service.aclose)
        if isinstance(service.embed_model, SupportsAclose):
            stack.push_async_callback(service.embed_model.aclose)
        resources.rag_service = service
