from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.modules.ai.llm.langfuse import (
    LangfuseLLMTracker,
    LLMTraceContext,
    build_langfuse_tracker,
)
from app.modules.ai.llm.router import ModelBuilder, ModelRole, ModelRouter

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage


@dataclass(frozen=True)
class LLMInstance:
    """The model dependency handlers receive: router + tracker.

    The model is resolved per call, because which target is healthy changes
    at runtime. ``ainvoke`` is the supported call path: it picks the target,
    attaches the trace config, reports the outcome to the breaker and, on a
    transient primary failure, retries once on the secondary.
    """

    router: ModelRouter
    tracker: LangfuseLLMTracker

    def trace_config(self, context: LLMTraceContext | None = None) -> dict[str, object]:
        return self.tracker.trace_config(context)

    async def ainvoke(
        self,
        input: Any,
        *,
        role: ModelRole = "default",
        context: LLMTraceContext | None = None,
    ) -> BaseMessage:
        target = self.router.select_target(role)
        try:
            message = await self._call(target, input, context)
        except Exception as exc:
            self.router.record_error(target, error=exc, role=role)
            fallback = self.router.failover_target(target, exc, role)
            if fallback is None:
                raise
            # The secondary has no breaker; its outcome is not tracked.
            return await self._call(fallback, input, context)
        self.router.record_success(target, role=role)
        return message

    def chat_model(self, role: ModelRole = "default") -> BaseChatModel:
        """Raw model for the next call (streaming, tool binding). Bypasses
        failover and outcome reporting; the caller owns both."""
        return self.router.chat_model(role)

    async def _call(
        self,
        target: str,
        input: Any,
        context: LLMTraceContext | None,
    ) -> BaseMessage:
        return await self.router.model_for(target).ainvoke(
            input,
            config=self.tracker.trace_config(context),  # type: ignore[arg-type]
        )


def build_llm_instance(
    settings: Settings,
    *,
    instance_id: str,
    service_name: str,
    tags: tuple[str, ...] = (),
    model_builder: ModelBuilder | None = None,
) -> LLMInstance:
    return LLMInstance(
        router=ModelRouter(settings, model_builder=model_builder),
        tracker=build_langfuse_tracker(
            settings,
            instance_id=instance_id,
            service_name=service_name,
            tags=tags,
        ),
    )
