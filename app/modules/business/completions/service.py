import asyncio
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from time import perf_counter, time_ns
from typing import Literal

from app.core.errors import AppError
from app.core.telemetry import (
    NOOP_SINK,
    CompletionObservation,
    CompletionSink,
    Outcome,
)
from app.modules.business.completions.guards import CompletionGuard
from app.modules.business.completions.ports import CompletionHandler
from app.modules.business.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
    StreamSummary,
)


@dataclass(frozen=True)
class StreamPolicy:
    first_token_timeout: float
    idle_timeout: float


# Matches the STREAM_*_TIMEOUT_SECONDS defaults; bootstrap passes the configured policy.
DEFAULT_POLICY = StreamPolicy(first_token_timeout=30, idle_timeout=30)


class StreamTimeoutError(AppError):
    def __init__(self, message: str = "Timed out waiting for the model") -> None:
        super().__init__(code="stream_timeout", message=message, status_code=504)


@dataclass
class _Observation:
    """Times one call and hands its metadata (never content) to the sink once."""

    mode: Literal["sync", "stream"]
    sink: CompletionSink
    summary: StreamSummary = field(default_factory=StreamSummary)
    started_at: float = field(default_factory=perf_counter)
    started_ns: int = field(default_factory=time_ns)
    ttft_s: float | None = None

    def mark_first_token(self) -> None:
        if self.ttft_s is None:
            self.ttft_s = perf_counter() - self.started_at

    def record(self, outcome: Outcome) -> None:
        usage = self.summary.usage
        self.sink.record_completion(
            CompletionObservation(
                mode=self.mode,
                outcome=outcome,
                started_ns=self.started_ns,
                duration_s=perf_counter() - self.started_at,
                ttft_s=self.ttft_s,
                model=self.summary.model,
                finish_reason=self.summary.finish_reason,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
            )
        )


class CompletionService:
    """Completion business service; behavior lives in the injected handler.

    Bootstrap builds exactly one instance per app, after resources open, and
    stores it on ``ApplicationResources.completion_service``. The API and the
    worker share it, so every completion is observed the same way: one
    ``CompletionObservation`` per ``complete``/``stream`` call.

    ``guards`` run in order, fail-closed: input guards before the handler, output
    guards on the handler's result. ``stream`` runs input guards only; output
    guards on streamed chunks are not applied yet. ``policy`` bounds how long
    ``stream`` waits for the first chunk and between chunks; a missed deadline
    raises ``StreamTimeoutError``. A failure raised before the first chunk
    surfaces on first iteration, so the API can still answer with a JSON error.
    """

    def __init__(
        self,
        handler: CompletionHandler,
        *,
        guards: Sequence[CompletionGuard] = (),
        sink: CompletionSink = NOOP_SINK,
        policy: StreamPolicy = DEFAULT_POLICY,
    ) -> None:
        self.handler = handler
        self.guards = tuple(guards)
        self.sink = sink
        self.policy = policy

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        observation = _Observation("sync", self.sink)
        outcome: Outcome = "disconnected"  # what a cancelled call means
        try:
            await self._check_input(request)
            result = await self.handler.complete(request)
            for guard in self.guards:
                await guard.check_output(request, result)
            observation.summary.merge(result)
            outcome = "ok"
            return result
        except Exception:
            outcome = "error"
            raise
        finally:
            observation.record(outcome)

    async def stream(
        self,
        request: CompletionRequest,
    ) -> AsyncGenerator[CompletionStreamChunk, None]:
        observation = _Observation("stream", self.sink)
        outcome: Outcome = "disconnected"  # what a closed or cancelled stream means
        chunks = None
        try:
            await self._check_input(request)
            chunks = self.handler.stream(request)
            deadline = self.policy.first_token_timeout
            while True:
                try:
                    async with asyncio.timeout(deadline):
                        chunk = await anext(chunks, None)
                except TimeoutError:
                    raise StreamTimeoutError from None
                if chunk is None:
                    break
                deadline = self.policy.idle_timeout
                observation.summary.merge(chunk)
                if chunk.delta:
                    observation.mark_first_token()
                yield chunk
            outcome = "ok"
        except StreamTimeoutError:
            outcome = "timeout"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            observation.record(outcome)
            if isinstance(chunks, AsyncGenerator):
                await chunks.aclose()

    async def _check_input(self, request: CompletionRequest) -> None:
        for guard in self.guards:
            await guard.check_input(request)
