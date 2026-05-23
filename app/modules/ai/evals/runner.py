from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.core.resilience import TimeoutPolicy
from app.modules.ai.evals.evaluators import EvalScore, Evaluator


@dataclass(frozen=True)
class EvalCase:
    id: str
    input: Any
    expected: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalTargetResult:
    output: Any
    trace_id: str | None = None
    observation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCaseResult:
    case: EvalCase
    output: Any
    scores: list[EvalScore]
    trace_id: str | None = None


@dataclass(frozen=True)
class EvalReport:
    results: list[EvalCaseResult]

    @property
    def total_cases(self) -> int:
        return len(self.results)

    @property
    def total_scores(self) -> int:
        return sum(len(result.scores) for result in self.results)

    @property
    def passed_scores(self) -> int:
        return sum(
            1
            for result in self.results
            for score in result.scores
            if score.passed is True
        )


EvalTarget = Callable[[EvalCase], Awaitable[EvalTargetResult | Any]]


class EvalScoreTracker(Protocol):
    """Minimal tracker surface used by eval runner.

    Concrete implementations (``LangfuseLLMTracker`` etc.) satisfy this via
    duck typing.
    """

    def score_trace(
        self,
        *,
        trace_id: str,
        name: str,
        value: float | str | bool,
        data_type: str,
        comment: str | None = None,
        observation_id: str | None = None,
    ) -> Any: ...


def load_jsonl_cases(path: str | Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        cases.append(
            EvalCase(
                id=str(raw["id"]),
                input=raw.get("input"),
                expected=raw.get("expected"),
                metadata=dict(raw.get("metadata") or {}),
            )
        )
    return cases


async def evaluate_one(
    *,
    output: Any,
    expected: Any = None,
    evaluators: Sequence[Evaluator],
    timeout: TimeoutPolicy | None = None,
) -> list[EvalScore]:
    """Score a single output against evaluators.

    Used for:
    - Inline gating (Pattern A): caller checks ``score.passed is False`` and
      raises before returning the response.
    - Async monitoring (Pattern B): called inside a queue task handler with
      the captured response payload.
    """

    async def _run() -> list[EvalScore]:
        scores: list[EvalScore] = []
        for evaluator in evaluators:
            result = evaluator.evaluate(output=output, expected=expected)
            if inspect.isawaitable(result):
                result = await result
            scores.append(result)
        return scores

    if timeout is None:
        return await _run()
    return await asyncio.wait_for(_run(), timeout=timeout.timeout_seconds)


def push_scores_to_tracker(
    tracker: EvalScoreTracker,
    *,
    trace_id: str,
    scores: Sequence[EvalScore],
    observation_id: str | None = None,
) -> None:
    """Forward evaluation scores to an external tracker (e.g. Langfuse)."""
    for score in scores:
        tracker.score_trace(
            trace_id=trace_id,
            observation_id=observation_id,
            name=score.name,
            value=score.value,
            data_type=score.data_type,
            comment=score.comment,
        )


async def run_eval_cases(
    cases: Sequence[EvalCase],
    *,
    target: EvalTarget,
    evaluators: Sequence[Evaluator],
    tracker: EvalScoreTracker | None = None,
    timeout: TimeoutPolicy | None = None,
) -> EvalReport:
    results: list[EvalCaseResult] = []
    for case in cases:
        raw_result = await target(case)
        target_result = _normalize_target_result(raw_result)
        scores = await evaluate_one(
            output=target_result.output,
            expected=case.expected,
            evaluators=evaluators,
            timeout=timeout,
        )
        if tracker is not None and target_result.trace_id:
            push_scores_to_tracker(
                tracker,
                trace_id=target_result.trace_id,
                observation_id=target_result.observation_id,
                scores=scores,
            )
        results.append(
            EvalCaseResult(
                case=case,
                output=target_result.output,
                scores=scores,
                trace_id=target_result.trace_id,
            )
        )
    return EvalReport(results=results)


def _normalize_target_result(result: EvalTargetResult | Any) -> EvalTargetResult:
    if isinstance(result, EvalTargetResult):
        return result
    return EvalTargetResult(output=result)
