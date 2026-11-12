"""Eval gate for the completions surface.

Runs the JSONL dataset against the CompletionService built by the completions
feature (echo handler by default — pass your product handler factory to
completions_feature when you fork) and FAILS (exit != 0)
when the pass rate drops below --min-score.

Per-case evaluator selection via metadata.evaluator: exact | contains |
judge. Judge cases need JUDGE_CHAT_MODEL (+ the [ai] extra); without it they
are SKIPPED so the gate stays hermetic in CI. An unknown value fails the gate
before any case is scored.

    python -m scripts.run_eval                    # default dataset + 0.8 gate
    python -m scripts.run_eval --cases evals/x.jsonl --min-score 0.9
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable

from app.bootstrap.features.completions import completions_feature
from app.bootstrap.resources import ApplicationResources
from app.core.config import get_settings
from app.modules.ai.evals.evaluators import (
    ContainsEvaluator,
    Evaluator,
    ExactMatchEvaluator,
    build_llm_judge,
)
from app.modules.ai.evals.runner import (
    EvalCase,
    EvalTargetResult,
    EvaluatorSelector,
    load_jsonl_cases,
    run_eval_cases,
)
from app.modules.business.completions.schemas import CompletionRequest

DEFAULT_CASES = "evals/completions_smoke.jsonl"
_EVALUATOR_KINDS = ("exact", "contains", "judge")


def _build_target(settings) -> Callable[[EvalCase], Awaitable[EvalTargetResult]]:
    service = completions_feature().build(ApplicationResources(), settings)

    async def target(case: EvalCase) -> EvalTargetResult:
        result = await service.complete(CompletionRequest(**case.input))
        return EvalTargetResult(output=result.content)

    return target


def _build_selector(cases: list[EvalCase], settings) -> EvaluatorSelector:
    for case in cases:
        kind = case.metadata.get("evaluator", "exact")
        if kind not in _EVALUATOR_KINDS:
            raise SystemExit(
                f"unknown evaluator {kind!r} in case {case.id!r}; "
                f"expected one of {', '.join(_EVALUATOR_KINDS)}"
            )
    judge: Evaluator | None = None
    if settings.JUDGE_CHAT_MODEL:
        judge = build_llm_judge(settings)
    by_kind: dict[str, Evaluator | None] = {
        "exact": ExactMatchEvaluator(),
        "contains": ContainsEvaluator(),
        "judge": judge,
    }

    def select(case: EvalCase) -> list[Evaluator]:
        evaluator = by_kind[case.metadata.get("evaluator", "exact")]
        return [] if evaluator is None else [evaluator]

    return select


async def _run(args: argparse.Namespace, settings=None) -> int:
    settings = settings or get_settings()
    cases = load_jsonl_cases(args.cases)
    selector = _build_selector(cases, settings)
    report = await run_eval_cases(
        cases, target=_build_target(settings), evaluators=selector
    )
    print(
        json.dumps(
            {
                "cases": report.total_cases,
                "scored": report.total_scores,
                "passed": report.passed_scores,
                "skipped_judge": report.skipped_cases,
                "pass_rate": round(report.pass_rate, 4),
                "min_score": args.min_score,
                "failures": report.failures,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if report.pass_rate >= args.min_score else 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=DEFAULT_CASES)
    parser.add_argument("--min-score", type=float, default=0.8)
    args = parser.parse_args(argv)
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
