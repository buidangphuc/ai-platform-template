"""One structured log line per completion (sync and stream).

Metadata only: latency, token usage, model and outcome. Never prompt or output
content. When telemetry is on, the same facts also go to the ``CompletionSink``
(GenAI metrics and a span); otherwise the sink is a no-op.
"""

from dataclasses import dataclass, field
from time import perf_counter, time_ns
from typing import Literal

from loguru import logger

from app.bootstrap.resources import ApplicationResources
from app.core.telemetry import NOOP_SINK, CompletionObservation, CompletionSink
from app.modules.business.completions.schemas import CompletionUsage

Mode = Literal["sync", "stream"]
Outcome = Literal["ok", "error", "timeout", "disconnected"]


def completion_sink(resources: ApplicationResources) -> CompletionSink:
    """The telemetry handle when it is open, else the no-op sink."""
    return resources.telemetry or NOOP_SINK


@dataclass
class CompletionTimer:
    mode: Mode
    sink: CompletionSink = NOOP_SINK
    started_at: float = field(default_factory=perf_counter)
    started_ns: int = field(default_factory=time_ns)
    ttft_ms: float | None = None
    model: str | None = None
    usage: CompletionUsage | None = None
    finish_reason: str | None = None

    def observe(
        self,
        *,
        model: str | None,
        usage: CompletionUsage | None,
        finish_reason: str | None,
    ) -> None:
        """Keep the latest non-empty value of each field (a stream reports late)."""
        self.model = model or self.model
        self.usage = usage or self.usage
        self.finish_reason = finish_reason or self.finish_reason

    def mark_first_token(self) -> None:
        if self.ttft_ms is None:
            self.ttft_ms = (perf_counter() - self.started_at) * 1000

    def emit(self, outcome: Outcome) -> None:
        duration_ms = (perf_counter() - self.started_at) * 1000
        usage = self.usage
        input_tokens = usage.input_tokens if usage else None
        output_tokens = usage.output_tokens if usage else None
        total_tokens = usage.total_tokens if usage else None
        logger.bind(
            event="completion",
            mode=self.mode,
            outcome=outcome,
            model=self.model,
            duration_ms=round(duration_ms, 1),
            ttft_ms=None if self.ttft_ms is None else round(self.ttft_ms, 1),
            finish_reason=self.finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        ).info(
            "completion mode={} outcome={} model={} duration_ms={:.1f} ttft_ms={} "
            "finish_reason={} input_tokens={} output_tokens={} total_tokens={}",
            self.mode,
            outcome,
            self.model,
            duration_ms,
            None if self.ttft_ms is None else round(self.ttft_ms, 1),
            self.finish_reason,
            input_tokens,
            output_tokens,
            total_tokens,
        )
        self.sink.record_completion(
            CompletionObservation(
                mode=self.mode,
                outcome=outcome,
                started_ns=self.started_ns,
                duration_s=duration_ms / 1000,
                ttft_s=None if self.ttft_ms is None else self.ttft_ms / 1000,
                model=self.model,
                finish_reason=self.finish_reason,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )
