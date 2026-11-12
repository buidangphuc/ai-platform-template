from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.telemetry import FanOutSink, LogLlmSink
from app.modules.ai.llm.langfuse import LangfuseLLMTracker
from app.modules.ai.llm.runtime import build_llm_instance


class LlmAddon:
    name = "llm"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.LLM_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        llm = build_llm_instance(
            settings,
            instance_id=settings.PROJECT_NAME,
            service_name=settings.PROJECT_NAME,
            sink=FanOutSink(
                [LogLlmSink(), *([resources.telemetry] if resources.telemetry else [])]
            ),
        )
        resources.llm = llm
        stack.callback(setattr, resources, "llm", None)
        if settings.LANGFUSE_ENABLED:
            stack.push_async_callback(_flush_tracker, llm.tracker)


async def _flush_tracker(tracker: LangfuseLLMTracker) -> None:
    await asyncio.to_thread(tracker.flush)
