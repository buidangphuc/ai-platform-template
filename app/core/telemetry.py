"""Telemetry contract that needs no OpenTelemetry install.

``LLMInstance`` reports each finished LLM call to a ``LlmSink``.
With telemetry off it is ``NOOP_SINK``; with it on, the OTel-backed handle in
``app/core/telemetry_otel.py`` (the optional ``otel`` extra) is the sink.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from loguru import logger

_HINT = "install the OTel extra: `uv sync --extra otel` (or `pip install '.[otel]'`)"

Outcome = Literal["ok", "error", "timeout", "disconnected"]


@dataclass(frozen=True)
class LlmObservation:
    """Metadata of one finished LLM call. Never prompt or output content."""

    mode: Literal["sync", "stream"]
    outcome: Outcome
    started_ns: int
    duration_s: float
    ttft_s: float | None
    model: str | None
    finish_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None = None


class LlmSink(Protocol):
    def record_llm(self, observation: LlmObservation) -> None: ...


class _NoopSink:
    def record_llm(self, observation: LlmObservation) -> None:
        return None


NOOP_SINK: LlmSink = _NoopSink()


class LogLlmSink:
    """One structured log line per LLM call: metadata only, never content."""

    def record_llm(self, observation: LlmObservation) -> None:
        duration_ms = observation.duration_s * 1000
        ttft_ms = (
            None if observation.ttft_s is None else round(observation.ttft_s * 1000, 1)
        )
        logger.bind(
            event="completion",
            mode=observation.mode,
            outcome=observation.outcome,
            model=observation.model,
            duration_ms=round(duration_ms, 1),
            ttft_ms=ttft_ms,
            finish_reason=observation.finish_reason,
            input_tokens=observation.input_tokens,
            output_tokens=observation.output_tokens,
            total_tokens=observation.total_tokens,
        ).info(
            "completion mode={} outcome={} model={} duration_ms={:.1f} ttft_ms={} "
            "finish_reason={} input_tokens={} output_tokens={} total_tokens={}",
            observation.mode,
            observation.outcome,
            observation.model,
            duration_ms,
            ttft_ms,
            observation.finish_reason,
            observation.input_tokens,
            observation.output_tokens,
            observation.total_tokens,
        )


class FanOutSink:
    def __init__(self, sinks: Sequence[LlmSink]) -> None:
        self.sinks = tuple(sinks)

    def record_llm(self, observation: LlmObservation) -> None:
        for sink in self.sinks:
            sink.record_llm(observation)


def require_otel() -> None:
    try:
        importlib.import_module("opentelemetry.sdk.trace")
    except ImportError as exc:
        raise RuntimeError(
            f"OpenTelemetry is required by OTEL_ENABLED — {_HINT}"
        ) from exc
