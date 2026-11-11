from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from time import perf_counter, time_ns
from typing import TYPE_CHECKING, Any, Literal

from app.core.config import Settings
from app.core.errors import AppError, ServiceUnavailableError
from app.core.resilience import is_transient_error
from app.core.telemetry import NOOP_SINK, LlmObservation, LlmSink, Outcome
from app.modules.ai.llm.langfuse import (
    LangfuseLLMTracker,
    LLMTraceContext,
    build_langfuse_tracker,
)
from app.modules.ai.llm.router import ModelBuilder, ModelRole, ModelRouter

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage, BaseMessageChunk


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


class StreamTimeoutError(AppError):
    def __init__(self, message: str = "Timed out waiting for the model") -> None:
        super().__init__(code="stream_timeout", message=message, status_code=504)


@dataclass
class _Call:
    """Times one LLM call and hands its metadata (never content) to the sink once."""

    mode: Literal["sync", "stream"]
    sink: LlmSink
    started_at: float = field(default_factory=perf_counter)
    started_ns: int = field(default_factory=time_ns)
    target: str | None = None
    model: str | None = None
    finish_reason: str | None = None
    ttft_s: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def observe(self, message: BaseMessage) -> None:
        metadata = message.response_metadata
        self.model = metadata.get("model_name") or metadata.get("model") or self.model
        self.finish_reason = metadata.get("finish_reason") or self.finish_reason
        usage = getattr(message, "usage_metadata", None)
        if usage:
            input_tokens = int(usage.get("input_tokens", 0))
            output_tokens = int(usage.get("output_tokens", 0))
            self.input_tokens = (self.input_tokens or 0) + input_tokens
            self.output_tokens = (self.output_tokens or 0) + output_tokens
            self.total_tokens = (self.total_tokens or 0) + int(
                usage.get("total_tokens", input_tokens + output_tokens)
            )
        if self.mode == "stream" and self.ttft_s is None and message.text:
            self.ttft_s = perf_counter() - self.started_at

    def record(self, outcome: Outcome) -> None:
        self.sink.record_llm(
            LlmObservation(
                mode=self.mode,
                outcome=outcome,
                started_ns=self.started_ns,
                duration_s=perf_counter() - self.started_at,
                ttft_s=self.ttft_s,
                model=self.model or self.target or None,
                finish_reason=self.finish_reason,
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                total_tokens=self.total_tokens,
            )
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

    Every ``ainvoke`` (mode ``sync``) and ``astream`` (mode ``stream``) call
    reports exactly one ``LlmObservation`` to ``sink``: outcome, duration,
    model, finish reason and token usage, never prompt or output content.
    """

    router: ModelRouter
    tracker: LangfuseLLMTracker
    sink: LlmSink = NOOP_SINK

    def trace_config(self, context: LLMTraceContext | None = None) -> dict[str, object]:
        return self.tracker.trace_config(context)

    async def ainvoke(
        self,
        input: Any,
        *,
        role: ModelRole = "default",
        context: LLMTraceContext | None = None,
    ) -> BaseMessage:
        call = _Call("sync", self.sink)
        outcome: Outcome = "disconnected"  # what a cancelled call means
        try:
            call.target, message = await self._invoke_chain(input, role, context)
            call.observe(message)
            outcome = "ok"
            return message
        except LLMDeadlineExceeded:
            outcome = "timeout"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            call.record(outcome)

    async def _invoke_chain(
        self,
        input: Any,
        role: ModelRole,
        context: LLMTraceContext | None,
    ) -> tuple[str, BaseMessage]:
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
                    self.router.release(target, role=role)
                    raise LLMDeadlineExceeded(deadline_seconds) from exc
                self.router.record_error(target, error=exc, role=role)
                if not is_transient_error(exc):
                    raise
                last_error = exc
                continue
            self.router.record_success(target, role=role)
            return target, message
        if last_error is not None:
            raise last_error
        raise ServiceUnavailableError(
            message="Every configured LLM target is unavailable",
            code="llm_unavailable",
        )

    async def astream(
        self,
        input: Any,
        *,
        role: ModelRole = "default",
        context: LLMTraceContext | None = None,
        first_token_timeout: float | None = None,
        idle_timeout: float | None = None,
    ) -> AsyncIterator[BaseMessageChunk]:
        """Stream the role's chain like ``ainvoke``.

        Failover happens only for a transient error raised before the first
        chunk; once a chunk was yielded an error propagates. The chain deadline
        bounds the wait for the first chunk of every attempt.
        ``first_token_timeout`` bounds the wait for the first chunk and
        ``idle_timeout`` the gap between chunks; a missed one raises
        ``StreamTimeoutError``. Like the chain deadline it is our budget, so the
        attempt is released without counting against the target's breaker.
        """
        call = _Call("stream", self.sink)
        outcome: Outcome = "disconnected"  # what a closed or cancelled stream means
        deadline_seconds = self.router.settings.LLM_CHAIN_DEADLINE_SECONDS
        loop = asyncio.get_running_loop()
        deadline = loop.time() + deadline_seconds
        last_error: Exception | None = None
        try:
            for target in self.router.chain(role):
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise LLMDeadlineExceeded(deadline_seconds) from last_error
                if not self.router.try_acquire(target, role):
                    continue
                chunks = self.router.model_for(target).astream(
                    input,
                    config=self.tracker.trace_config(context),  # type: ignore[arg-type]
                )
                started = False
                settled = False
                try:
                    while True:
                        try:
                            async with (
                                asyncio.timeout(
                                    None if started else remaining
                                ) as budget,
                                asyncio.timeout(
                                    idle_timeout if started else first_token_timeout
                                ) as stall,
                            ):
                                chunk = await anext(chunks)
                        except StopAsyncIteration:
                            self.router.record_success(target, role=role)
                            settled = True
                            outcome = "ok"
                            return
                        except Exception as exc:
                            settled = True
                            if stall.expired():
                                self.router.release(target, role=role)
                                raise StreamTimeoutError from None
                            if budget.expired():
                                self.router.release(target, role=role)
                                raise LLMDeadlineExceeded(deadline_seconds) from exc
                            self.router.record_error(target, error=exc, role=role)
                            if started or not is_transient_error(exc):
                                raise
                            last_error = exc
                            break
                        started = True
                        call.target = target
                        call.observe(chunk)
                        yield chunk
                finally:
                    if not settled:
                        self.router.release(target, role=role)
                    if isinstance(chunks, AsyncGenerator):
                        await chunks.aclose()
            if last_error is not None:
                raise last_error
            raise ServiceUnavailableError(
                message="Every configured LLM target is unavailable",
                code="llm_unavailable",
            )
        except (LLMDeadlineExceeded, StreamTimeoutError):
            outcome = "timeout"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            call.record(outcome)

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
    sink: LlmSink = NOOP_SINK,
) -> LLMInstance:
    return LLMInstance(
        router=ModelRouter(settings, model_builder=model_builder),
        sink=sink,
        tracker=build_langfuse_tracker(
            settings,
            instance_id=instance_id,
            service_name=service_name,
            tags=tags,
        ),
    )
