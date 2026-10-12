from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.core.errors import AppError, ServiceUnavailableError
from app.core.resilience import is_transient_error
from app.modules.ai.llm.langfuse import (
    LangfuseLLMTracker,
    LLMTraceContext,
    build_langfuse_tracker,
)
from app.modules.ai.llm.router import ModelBuilder, ModelRole, ModelRouter

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage


class LLMDeadlineExceeded(AppError):
    """The fallback chain used up ``LLM_CHAIN_DEADLINE_SECONDS``.

    A 504 carries ``status_code`` >= 500, so ``is_transient_error`` classifies
    it as transient: callers may retry the whole request later.
    """

    def __init__(self, deadline_seconds: float) -> None:
        super().__init__(
            code="llm_deadline_exceeded",
            message=f"LLM call exceeded its {deadline_seconds:g}s overall deadline",
            status_code=504,
        )


@dataclass(frozen=True)
class LLMInstance:
    """The model dependency handlers receive: router + tracker.

    The model is resolved per call, because which target is healthy changes
    at runtime. ``ainvoke`` is the supported call path: it walks the role's
    chain in order, skipping targets whose breaker is open, attaches the trace
    config, reports each outcome to that target's breaker and moves on to the
    next target only after a transient failure. A deterministic error
    propagates at once; when every target fails the last error is raised, and
    when every breaker is open ``ServiceUnavailableError``.

    The whole walk shares one ``LLM_CHAIN_DEADLINE_SECONDS`` budget: each
    attempt runs under what is left of it, and when it runs out the walk stops
    with ``LLMDeadlineExceeded``. An attempt cut short by the deadline is our
    budget, not the provider's fault, so it is not reported to the breaker.
    The per-request ``LLM_TIMEOUT_SECONDS`` stays the SDK's job.
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
        deadline_seconds = self.router.settings.LLM_CHAIN_DEADLINE_SECONDS
        loop = asyncio.get_running_loop()
        deadline = loop.time() + deadline_seconds
        last_error: Exception | None = None
        for target in self.router.chain(role):
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise LLMDeadlineExceeded(deadline_seconds) from last_error
            if not self.router.try_acquire(target, role):
                continue
            try:
                async with asyncio.timeout(remaining) as budget:
                    message = await self._call(target, input, context)
            except Exception as exc:
                if budget.expired():
                    raise LLMDeadlineExceeded(deadline_seconds) from exc
                self.router.record_error(target, error=exc, role=role)
                if not is_transient_error(exc):
                    raise
                last_error = exc
                continue
            self.router.record_success(target, role=role)
            return message
        if last_error is not None:
            raise last_error
        raise ServiceUnavailableError(
            message="Every configured LLM target is unavailable",
            code="llm_unavailable",
        )

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
