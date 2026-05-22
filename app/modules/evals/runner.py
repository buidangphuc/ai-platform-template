from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.modules.evals.evaluators import EvalScore, Evaluator


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
            1 for result in self.results for score in result.scores if score.passed
        )


EvalTarget = Callable[[EvalCase], Awaitable[EvalTargetResult | Any]]


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


async def run_eval_cases(
    cases: Sequence[EvalCase],
    *,
    target: EvalTarget,
    evaluators: Sequence[Evaluator],
    tracker: Any | None = None,
) -> EvalReport:
    results: list[EvalCaseResult] = []
    for case in cases:
        raw_result = await target(case)
        target_result = _normalize_target_result(raw_result)
        scores = [
            evaluator.evaluate(output=target_result.output, expected=case.expected)
            for evaluator in evaluators
        ]
        if tracker is not None and target_result.trace_id:
            for score in scores:
                tracker.score_trace(
                    trace_id=target_result.trace_id,
                    observation_id=target_result.observation_id,
                    name=score.name,
                    value=score.value,
                    data_type=score.data_type,
                    comment=score.comment,
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
