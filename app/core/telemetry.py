"""Telemetry contract that needs no OpenTelemetry install.

The completions edge reports each finished completion to a ``CompletionSink``.
With telemetry off it is ``NOOP_SINK``; with it on, the OTel-backed handle in
``app/core/telemetry_otel.py`` (the optional ``otel`` extra) is the sink.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Literal, Protocol

_HINT = "install the OTel extra: `uv sync --extra otel` (or `pip install '.[otel]'`)"

Outcome = Literal["ok", "error", "timeout", "disconnected"]


@dataclass(frozen=True)
class CompletionObservation:
    """Metadata of one finished completion. Never prompt or output content."""

    mode: Literal["sync", "stream"]
    outcome: Outcome
    started_ns: int
    duration_s: float
    ttft_s: float | None
    model: str | None
    finish_reason: str | None
    input_tokens: int | None
    output_tokens: int | None


class CompletionSink(Protocol):
    def record_completion(self, observation: CompletionObservation) -> None: ...


class _NoopSink:
    def record_completion(self, observation: CompletionObservation) -> None:
        return None


NOOP_SINK: CompletionSink = _NoopSink()


def require_otel() -> None:
    try:
        importlib.import_module("opentelemetry.sdk.trace")
    except ImportError as exc:
        raise RuntimeError(
            f"OpenTelemetry is required by OTEL_ENABLED — {_HINT}"
        ) from exc
